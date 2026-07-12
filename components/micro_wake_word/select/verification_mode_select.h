#pragma once

#ifdef USE_ESP32

#include "../micro_wake_word.h"

#include "esphome/components/select/select.h"
#include "esphome/core/component.h"
#include "esphome/core/defines.h"
#include "esphome/core/preferences.h"

#ifdef USE_VOICE_ASSISTANT
#include "esphome/components/voice_assistant/voice_assistant.h"
#endif

namespace esphome::micro_wake_word {

/// Where wake word verification happens. Fixed options, in index order:
/// Off / On-device / Home Assistant / Both. The Home Assistant modes are
/// refused at selection time while the HA wake engine entity (openWakeWord)
/// is unavailable — the ESPHome API cannot grey out select options, so the
/// pick is rejected with a warning instead. The choice persists in flash.
class VerificationModeSelect : public select::Select, public Component, public Parented<MicroWakeWord> {
 public:
  void setup() override;
  void dump_config() override;

#ifdef USE_VOICE_ASSISTANT
  void set_voice_assistant(voice_assistant::VoiceAssistant *va) { this->voice_assistant_ = va; }
#endif
  void set_initial_index(size_t index) { this->initial_index_ = index; }

 protected:
  void control(const std::string &value) override;
  void apply_(size_t index);
  bool ha_available_() const;

#ifdef USE_VOICE_ASSISTANT
  voice_assistant::VoiceAssistant *voice_assistant_{nullptr};
#endif
  size_t initial_index_{1};  // On-device
  ESPPreferenceObject pref_;
};

}  // namespace esphome::micro_wake_word

#endif  // USE_ESP32
