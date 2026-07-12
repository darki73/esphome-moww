#include "sensitivity_select.h"

#ifdef USE_ESP32

#include "esphome/core/log.h"

namespace esphome::micro_wake_word {

static const char *const TAG = "micro_wake_word.select";

void SensitivitySelect::setup() {
  size_t restored = 0;
  this->pref_ = global_preferences->make_preference<size_t>(this->get_object_id_hash());
  bool have_saved = this->pref_.load(&restored) && restored < this->presets_.size();

  const auto &options = this->traits.get_options();
  size_t initial = have_saved ? restored : this->initial_index_;
  this->apply_(initial);
  this->publish_state(std::string(options[initial]));
}

void SensitivitySelect::control(const std::string &value) {
  auto index = this->index_of(value);
  if (!index.has_value()) {
    ESP_LOGW(TAG, "Unknown sensitivity option '%s'", value.c_str());
    return;
  }
  this->apply_(index.value());
  size_t saved = index.value();
  this->pref_.save(&saved);
  this->publish_state(value);
}

void SensitivitySelect::apply_(size_t index) {
  if (index >= this->presets_.size()) {
    return;
  }
  const Preset &preset = this->presets_[index];
  for (auto *model : this->parent_->get_wake_words()) {
    if (!model->get_internal_only()) {
      model->set_probability_cutoff(preset.model_cutoff);
    }
  }
#ifdef USE_MICRO_WAKE_WORD_VERIFIER
  VerifierModel *verifier = this->parent_->get_verifier_model();
  if (verifier != nullptr) {
    verifier->set_probability_cutoff(preset.verifier_cutoff);
  }
#endif
  ESP_LOGD(TAG, "Sensitivity preset %u: model cutoff %u, verifier cutoff %u", (unsigned) index,
           preset.model_cutoff, preset.verifier_cutoff);
}

void SensitivitySelect::dump_config() { LOG_SELECT("", "Wake word sensitivity select", this); }

}  // namespace esphome::micro_wake_word

#endif  // USE_ESP32
