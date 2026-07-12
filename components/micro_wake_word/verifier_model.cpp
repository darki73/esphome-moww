#include "verifier_model.h"

#ifdef USE_ESP32
#ifdef USE_MICRO_WAKE_WORD_VERIFIER

#include "esphome/core/hal.h"
#include "esphome/core/helpers.h"
#include "esphome/core/log.h"

#include <cstring>

namespace esphome::micro_wake_word {

static const char *const TAG = "micro_wake_word.verifier";

// A MicroInterpreter whose AllocateTensors() FAILED must not be destructed:
// there is a failure window where the subgraph allocations array exists but
// node tables are uninitialized, and ~MicroInterpreter -> FreeSubgraphs()
// then walks garbage pointers (observed LoadProhibited on core 1). The
// interpreter owns nothing outside our arena, so freeing its heap memory
// without the destructor is safe and leak-free.
static void discard_failed_interpreter(std::unique_ptr<tflite::MicroInterpreter> &interpreter) {
  ::operator delete(static_cast<void *>(interpreter.release()));
}

bool VerifierModel::load_model() {
  if (this->loaded_) {
    return true;
  }

  if (!this->ops_registered_) {
    if (!this->register_ops_(this->op_resolver_)) {
      ESP_LOGE(TAG, "Failed to register the verifier model's TensorFlow operations");
      return false;
    }
    this->ops_registered_ = true;
  }

  const tflite::Model *model = tflite::GetModel(this->model_start_);
  if (model->version() != TFLITE_SCHEMA_VERSION) {
    ESP_LOGE(TAG, "Verifier model's schema is not supported");
    return false;
  }

  RAMAllocator<uint8_t> arena_allocator;

  // The non-streaming model has no manifest, so the configured arena size is a guess;
  // escalate if it is too small. Aligns test sizes to 16 bytes.
  size_t attempt_sizes[] = {(this->tensor_arena_size_ + 15) & ~15, (this->tensor_arena_size_ * 3 / 2 + 15) & ~15,
                            (this->tensor_arena_size_ * 2 + 15) & ~15};

  for (size_t attempt_size : attempt_sizes) {
    uint8_t *arena = arena_allocator.allocate(attempt_size);
    if (arena == nullptr) {
      continue;
    }

    auto interpreter = make_unique<tflite::MicroInterpreter>(model, this->op_resolver_, arena, attempt_size);
    if (interpreter->AllocateTensors() != kTfLiteOk) {
      discard_failed_interpreter(interpreter);
      arena_allocator.deallocate(arena, attempt_size);
      continue;
    }

    TfLiteTensor *input = interpreter->input(0);
    if ((input->dims->size != 3) || (input->dims->data[0] != 1) ||
        (input->dims->data[2] != PREPROCESSOR_FEATURE_SIZE)) {
      ESP_LOGE(TAG, "Verifier model input tensor has improper dimensions; expected [1, frames, %u]",
               PREPROCESSOR_FEATURE_SIZE);
      interpreter.reset();
      arena_allocator.deallocate(arena, attempt_size);
      return false;
    }
    if (input->type != kTfLiteInt8) {
      ESP_LOGE(TAG, "Verifier model input tensor is not int8");
      interpreter.reset();
      arena_allocator.deallocate(arena, attempt_size);
      return false;
    }

    TfLiteTensor *output = interpreter->output(0);
    if ((output->type != kTfLiteUInt8) && (output->type != kTfLiteInt8)) {
      ESP_LOGE(TAG, "Verifier model output tensor is neither uint8 nor int8");
      interpreter.reset();
      arena_allocator.deallocate(arena, attempt_size);
      return false;
    }

    this->window_frames_ = input->dims->data[1];
    this->tensor_arena_ = arena;
    this->allocated_arena_size_ = attempt_size;
    this->interpreter_ = std::move(interpreter);
    this->loaded_ = true;

    ESP_LOGD(TAG, "Verifier model loaded: window %zu frames, arena %zu bytes (%zu used)", this->window_frames_,
             attempt_size, this->interpreter_->arena_used_bytes());
    return true;
  }

  ESP_LOGE(TAG, "Could not allocate the verifier model's tensor arena");
  return false;
}

void VerifierModel::unload_model() {
  this->interpreter_.reset();

  if (this->tensor_arena_ != nullptr) {
    RAMAllocator<uint8_t> arena_allocator;
    arena_allocator.deallocate(this->tensor_arena_, this->allocated_arena_size_);
    this->tensor_arena_ = nullptr;
    this->allocated_arena_size_ = 0;
  }

  this->window_frames_ = 0;
  this->loaded_ = false;
}

int VerifierModel::score(const int8_t *features) {
  if (!this->loaded_) {
    return -1;
  }

  TfLiteTensor *input = this->interpreter_->input(0);
  std::memcpy(tflite::GetTensorData<int8_t>(input), features, this->window_frames_ * PREPROCESSOR_FEATURE_SIZE);

  if (this->interpreter_->Invoke() != kTfLiteOk) {
    ESP_LOGW(TAG, "Verifier interpreter invoke failed");
    return -1;
  }

  TfLiteTensor *output = this->interpreter_->output(0);
  if (output->type == kTfLiteUInt8) {
    return output->data.uint8[0];
  }
  // int8 output: shift zero point to map onto the 0-255 range
  return static_cast<int>(output->data.int8[0]) + 128;
}

bool VerifierModel::register_ops_(tflite::MicroMutableOpResolver<18> &op_resolver) {
  // The non-streaming export uses the streaming model's op set minus the
  // resource-variable streaming ops (CallOnce, VarHandle, ReadVariable, AssignVariable)
  if (op_resolver.AddReshape() != kTfLiteOk)
    return false;
  if (op_resolver.AddStridedSlice() != kTfLiteOk)
    return false;
  if (op_resolver.AddConcatenation() != kTfLiteOk)
    return false;
  if (op_resolver.AddConv2D() != kTfLiteOk)
    return false;
  if (op_resolver.AddMul() != kTfLiteOk)
    return false;
  if (op_resolver.AddAdd() != kTfLiteOk)
    return false;
  if (op_resolver.AddMean() != kTfLiteOk)
    return false;
  if (op_resolver.AddFullyConnected() != kTfLiteOk)
    return false;
  if (op_resolver.AddLogistic() != kTfLiteOk)
    return false;
  if (op_resolver.AddQuantize() != kTfLiteOk)
    return false;
  if (op_resolver.AddDepthwiseConv2D() != kTfLiteOk)
    return false;
  if (op_resolver.AddAveragePool2D() != kTfLiteOk)
    return false;
  if (op_resolver.AddMaxPool2D() != kTfLiteOk)
    return false;
  if (op_resolver.AddPad() != kTfLiteOk)
    return false;
  if (op_resolver.AddPack() != kTfLiteOk)
    return false;
  if (op_resolver.AddSplitV() != kTfLiteOk)
    return false;
  // The wakegen-native (contract v2 era) verifier export emits the
  // [B,T,40] -> [B,T,1,40] step as a literal EXPAND_DIMS with a SHAPE
  // helper, where the old SavedModel path folded it into a static RESHAPE
  if (op_resolver.AddExpandDims() != kTfLiteOk)
    return false;
  if (op_resolver.AddShape() != kTfLiteOk)
    return false;

  return true;
}

}  // namespace esphome::micro_wake_word

#endif  // USE_MICRO_WAKE_WORD_VERIFIER
#endif  // USE_ESP32
