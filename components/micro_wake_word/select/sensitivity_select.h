#pragma once

#ifdef USE_ESP32

#include "../micro_wake_word.h"

#include "esphome/components/select/select.h"
#include "esphome/core/component.h"
#include "esphome/core/preferences.h"

#include <vector>

namespace esphome::micro_wake_word {

/// Sensitivity presets: each option pairs a stage-1 streaming cutoff
/// (applied to every non-internal wake word model) with a stage-2 verifier
/// cutoff. The chosen option persists in flash.
class SensitivitySelect : public select::Select, public Component, public Parented<MicroWakeWord> {
 public:
  void setup() override;
  void dump_config() override;

  void add_preset(uint8_t model_cutoff, uint8_t verifier_cutoff) {
    this->presets_.push_back({model_cutoff, verifier_cutoff});
  }
  void set_initial_index(size_t index) { this->initial_index_ = index; }

 protected:
  struct Preset {
    uint8_t model_cutoff;
    uint8_t verifier_cutoff;
  };

  void control(const std::string &value) override;
  void apply_(size_t index);

  std::vector<Preset> presets_;
  size_t initial_index_{0};
  ESPPreferenceObject pref_;
};

}  // namespace esphome::micro_wake_word

#endif  // USE_ESP32
