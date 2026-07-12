#pragma once

#include "esphome/core/defines.h"

#ifdef USE_ESP32
#ifdef USE_MICRO_WAKE_WORD_VERIFIER

#include "preprocessor_settings.h"

#include <tensorflow/lite/core/c/common.h>
#include <tensorflow/lite/micro/micro_interpreter.h>
#include <tensorflow/lite/micro/micro_mutable_op_resolver.h>

#include <memory>

namespace esphome::micro_wake_word {

// One-shot (non-streaming) wake word verifier. After a streaming model reports
// a candidate, this model re-scores the entire spectrogram window at once.
// The model is the non-streaming quantized export of a microWakeWord training
// run (tflite_non_stream_quant/non_stream_quant.tflite).
class VerifierModel {
 public:
  VerifierModel(const uint8_t *model_start, uint8_t probability_cutoff, size_t tensor_arena_size)
      : model_start_(model_start), probability_cutoff_(probability_cutoff), tensor_arena_size_(tensor_arena_size) {}

  /// @brief Allocates the tensor arena and sets up the interpreter.
  /// Escalates the arena size if the configured size is too small.
  /// @return True if successful, false otherwise
  bool load_model();

  /// @brief Destroys the interpreter and frees the tensor arena
  void unload_model();

  bool is_loaded() const { return this->loaded_; }

  /// @brief Number of feature frames the model expects; valid only after load_model() succeeds
  size_t get_window_frames() const { return this->window_frames_; }

  /// @brief Runs one inference over get_window_frames() feature frames laid out
  /// [window_frames][PREPROCESSOR_FEATURE_SIZE].
  /// @return The quantized probability (0-255) or -1 on inference error
  int score(const int8_t *features);

  // Quantized probability cutoff mapping 0.0 - 1.0 to 0 - 255
  uint8_t get_probability_cutoff() const { return this->probability_cutoff_; }
  void set_probability_cutoff(uint8_t probability_cutoff) { this->probability_cutoff_ = probability_cutoff; }

  void set_enabled(bool enabled) { this->enabled_ = enabled; }
  bool is_enabled() const { return this->enabled_; }

 protected:
  /// @brief Returns true if all TensorFlow operations the non-streaming model needs were registered
  bool register_ops_(tflite::MicroMutableOpResolver<17> &op_resolver);

  const uint8_t *model_start_;
  uint8_t probability_cutoff_;
  size_t tensor_arena_size_;
  size_t window_frames_{0};

  bool loaded_{false};
  bool enabled_{true};

  uint8_t *tensor_arena_{nullptr};
  size_t allocated_arena_size_{0};
  std::unique_ptr<tflite::MicroInterpreter> interpreter_;
  tflite::MicroMutableOpResolver<17> op_resolver_;
};

}  // namespace esphome::micro_wake_word

#endif  // USE_MICRO_WAKE_WORD_VERIFIER
#endif  // USE_ESP32
