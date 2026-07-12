#include "verification_mode_select.h"

#ifdef USE_ESP32

#include "esphome/core/log.h"

namespace esphome::micro_wake_word {

static const char *const TAG = "micro_wake_word.select";

// Fixed option indices; the codegen registers the options in this order
static const size_t MODE_OFF = 0;
static const size_t MODE_ON_DEVICE = 1;
static const size_t MODE_HOME_ASSISTANT = 2;
static const size_t MODE_BOTH = 3;

static bool mode_uses_ha(size_t index) { return index == MODE_HOME_ASSISTANT || index == MODE_BOTH; }
static bool mode_uses_verifier(size_t index) { return index == MODE_ON_DEVICE || index == MODE_BOTH; }

void VerificationModeSelect::setup() {
  size_t restored = 0;
  this->pref_ = global_preferences->make_preference<size_t>(this->get_object_id_hash());
  bool have_saved = this->pref_.load(&restored) && restored <= MODE_BOTH;

  size_t initial = have_saved ? restored : this->initial_index_;
  // A restored HA mode stays selected even if the engine is not up yet at
  // boot (HA usually connects later); the voice assistant re-checks
  // availability on every pipeline start and passes through if it is gone.
  this->apply_(initial);
  const auto &options = this->traits.get_options();
  this->publish_state(std::string(options[initial]));
}

void VerificationModeSelect::control(const std::string &value) {
  auto index = this->index_of(value);
  if (!index.has_value()) {
    ESP_LOGW(TAG, "Unknown verification mode '%s'", value.c_str());
    return;
  }
  if (mode_uses_ha(index.value()) && !this->ha_available_()) {
    ESP_LOGW(TAG, "Rejecting '%s': Home Assistant wake engine is not available", value.c_str());
    // Re-publish the current option so the frontend snaps back
    this->publish_state(std::string(this->current_option()));
    return;
  }
  this->apply_(index.value());
  size_t saved = index.value();
  this->pref_.save(&saved);
  this->publish_state(value);
}

bool VerificationModeSelect::ha_available_() const {
#ifdef USE_VOICE_ASSISTANT
  return this->voice_assistant_ != nullptr && this->voice_assistant_->ha_verification_available();
#else
  return false;
#endif
}

void VerificationModeSelect::apply_(size_t index) {
#ifdef USE_MICRO_WAKE_WORD_VERIFIER
  VerifierModel *verifier = this->parent_->get_verifier_model();
  if (verifier != nullptr) {
    verifier->set_enabled(mode_uses_verifier(index));
  }
#endif
#ifdef USE_VOICE_ASSISTANT
  if (this->voice_assistant_ != nullptr) {
    this->voice_assistant_->set_ha_wake_word_verification(mode_uses_ha(index));
  }
#endif
  ESP_LOGD(TAG, "Verification mode %u (verifier %s, HA %s)", (unsigned) index,
           mode_uses_verifier(index) ? "on" : "off", mode_uses_ha(index) ? "on" : "off");
}

void VerificationModeSelect::dump_config() { LOG_SELECT("", "Verification mode select", this); }

}  // namespace esphome::micro_wake_word

#endif  // USE_ESP32
