#pragma once

#ifdef USE_ESP32

#include "preprocessor_settings.h"
#include "streaming_model.h"
#include "verifier_model.h"  // Self-guarded on USE_MICRO_WAKE_WORD_VERIFIER

#include "esphome/components/microphone/microphone_source.h"
#include "esphome/components/ring_buffer/ring_buffer.h"

#include "esphome/core/automation.h"
#include "esphome/core/component.h"
#include "esphome/core/defines.h"
#include "esphome/core/static_task.h"

#ifdef USE_OTA_STATE_LISTENER
#include "esphome/components/ota/ota_backend.h"
#endif

#include <freertos/event_groups.h>

#include <frontend.h>
#include <frontend_util.h>

namespace esphome::micro_wake_word {

enum State {
  STARTING,
  DETECTING_WAKE_WORD,
  STOPPING,
  STOPPED,
};

class MicroWakeWord : public Component
#ifdef USE_OTA_STATE_LISTENER
    ,
                      public ota::OTAGlobalStateListener
#endif
{
 public:
  void setup() override;
  void loop() override;
  float get_setup_priority() const override;
  void dump_config() override;

#ifdef USE_OTA_STATE_LISTENER
  void on_ota_global_state(ota::OTAState state, float progress, uint8_t error, ota::OTAComponent *comp) override;
#endif

  void start();
  void stop();

  bool is_running() const { return this->state_ != State::STOPPED; }

  void set_features_step_size(uint8_t step_size) { this->features_step_size_ = step_size; }

  void set_microphone_source(microphone::MicrophoneSource *microphone_source) {
    this->microphone_source_ = microphone_source;
  }

  void set_stop_after_detection(bool stop_after_detection) { this->stop_after_detection_ = stop_after_detection; }

  void set_task_stack_in_psram(bool task_stack_in_psram) { this->task_stack_in_psram_ = task_stack_in_psram; }

  Trigger<std::string> *get_wake_word_detected_trigger() { return &this->wake_word_detected_trigger_; }

  void add_wake_word_model(WakeWordModel *model);

#ifdef USE_MICRO_WAKE_WORD_VAD
  void add_vad_model(const uint8_t *model_start, uint8_t probability_cutoff, size_t sliding_window_size,
                     size_t tensor_arena_size);

  // Intended for the voice assistant component to fetch VAD status
  bool get_vad_state() { return this->vad_state_; }
#endif

  // Intended for the voice assistant component to access which wake words are available
  // Since these are pointers to the WakeWordModel objects, the voice assistant component can enable or disable them
  std::vector<WakeWordModel *> get_wake_words();

#ifdef USE_MICRO_WAKE_WORD_VERIFIER
  void set_verifier_model(VerifierModel *verifier_model) { this->verifier_model_ = verifier_model; }
  VerifierModel *get_verifier_model() { return this->verifier_model_; }
#endif

#ifdef USE_MICRO_WAKE_WORD_PCM_HISTORY
  void set_pcm_history_duration(uint32_t duration_ms) { this->pcm_history_duration_ms_ = duration_ms; }

  /// @brief Copies up to max_samples of the most recent audio history into dst, oldest sample first.
  /// @return The number of samples copied
  size_t copy_pcm_history(int16_t *dst, size_t max_samples);
#endif

 protected:
  microphone::MicrophoneSource *microphone_source_{nullptr};
  Trigger<std::string> wake_word_detected_trigger_;
  State state_{State::STOPPED};

  std::weak_ptr<ring_buffer::RingBuffer> ring_buffer_;
  std::vector<WakeWordModel *> wake_word_models_;

#ifdef USE_MICRO_WAKE_WORD_VAD
  std::unique_ptr<VADModel> vad_model_;
  bool vad_state_{false};
#endif

  bool pending_start_{false};
  bool pending_stop_{false};

  bool stop_after_detection_;

  bool task_stack_in_psram_{false};

  uint8_t features_step_size_;

  // Audio frontend handles generating spectrogram features
  struct FrontendConfig frontend_config_;
  struct FrontendState frontend_state_;

  // Handles managing the stop/state of the inference task
  EventGroupHandle_t event_group_;

  // Used to send messages about the models' states to the main loop
  QueueHandle_t detection_queue_;

  StaticTask inference_task_;

  static void inference_task(void *params);

  /// @brief Suspends the inference task
  void suspend_task_();
  /// @brief Resumes the inference task
  void resume_task_();

  void set_state_(State state);

  /// @brief Generates a spectrogram feature from an input buffer of audio samples. The frontend buffers samples
  /// internally, so callers may stream arbitrary-sized chunks; a feature is only emitted once enough samples have
  /// accumulated to fill a full analysis window.
  /// @param audio_buffer (const int16_t *) Buffer containing input audio samples
  /// @param samples_available (size_t) Number of samples available in the input buffer
  /// @param features_buffer (int8_t *) Buffer to store the generated feature, valid only when the return value is true
  /// @param processed_samples (size_t *) Set to the number of samples consumed from the input buffer
  /// @return True if a new feature was generated; false if more samples are required
  bool generate_features_(const int16_t *audio_buffer, size_t samples_available,
                          int8_t features_buffer[PREPROCESSOR_FEATURE_SIZE], size_t *processed_samples);

  /// @brief Processes any new probabilities for each model. If any wake word is detected, it will send a DetectionEvent
  /// to the detection_queue_.
  void process_probabilities_();

#ifdef USE_MICRO_WAKE_WORD_VERIFIER
  VerifierModel *verifier_model_{nullptr};

  // Rolling history of the most recent spectrogram features; written only by the inference task
  int8_t *feature_history_{nullptr};
  size_t feature_history_capacity_{0};  // frames
  size_t feature_history_next_{0};
  size_t feature_history_count_{0};

  // Scratch buffer holding the contiguous window handed to the verifier
  int8_t *verifier_input_{nullptr};
  size_t verifier_input_frames_{0};  // Allocation size, kept separately so freeing never depends on model state

  /// @brief Appends one feature frame to the rolling history. Runs on the inference task.
  void store_feature_history_(const int8_t features[PREPROCESSOR_FEATURE_SIZE]);

  /// @brief Allocates the feature history and scratch buffers; requires a loaded verifier model.
  bool allocate_verifier_buffers_();
  void free_verifier_buffers_();

  /// @brief Re-scores the candidate with the one-shot verifier model. Runs on the inference task.
  /// Fails open: if the verifier is unavailable or errors, the event is returned unchanged.
  DetectionEvent run_verifier_(const DetectionEvent &event);

  // Deferred verification: stage 1 is greedy and fires while the wake word
  // is still being spoken, but the verifier is trained on windows where the
  // word has COMPLETED (measured on-device: mid-word windows score ~0.12,
  // completed windows 0.7+). A candidate therefore waits until the word's
  // tail is in the feature history: scored twice, ~150 ms and ~300 ms after
  // the candidate, early-exiting on the first confirmation.
  DetectionEvent pending_verify_event_{};
  bool verify_pending_{false};
  uint16_t verify_frames_waited_{0};
  int verify_best_score_{-1};

  /// @brief Advances a pending deferred verification by one feature frame;
  /// enqueues the detection when a scoring point confirms it. Runs on the
  /// inference task, once per generated feature.
  void tick_pending_verification_();
#endif

#ifdef USE_MICRO_WAKE_WORD_PCM_HISTORY
  // Rolling history of raw audio for network verification pre-roll; written by the microphone data callback
  int16_t *pcm_history_{nullptr};
  size_t pcm_history_capacity_{0};  // samples
  volatile size_t pcm_history_next_{0};
  volatile bool pcm_history_full_{false};
  uint32_t pcm_history_duration_ms_{3000};

  void write_pcm_history_(const uint8_t *data, size_t len);
#endif

  /// @brief Deletes each model's TFLite interpreters and frees tensor arena memory.
  void unload_models_();

  /// @brief Runs an inference with each model using the new spectrogram features
  /// @param audio_features (int8_t *) Buffer containing new spectrogram features
  /// @return True if successful, false if any errors were encountered
  bool update_model_probabilities_(const int8_t audio_features[PREPROCESSOR_FEATURE_SIZE]);
};

}  // namespace esphome::micro_wake_word

#endif  // USE_ESP32
