#include "verifier_switch.h"

#ifdef USE_ESP32
#ifdef USE_MICRO_WAKE_WORD_VERIFIER

#include "esphome/core/log.h"

namespace esphome::micro_wake_word {

static const char *const TAG = "micro_wake_word.switch";

void VerifierSwitch::setup() {
  bool initial = this->get_initial_state_with_restore_mode().value_or(true);
  // publish_state calls write_state, which applies it to the verifier
  this->publish_state(initial);
}

void VerifierSwitch::write_state(bool state) {
  VerifierModel *verifier = this->parent_->get_verifier_model();
  if (verifier != nullptr) {
    verifier->set_enabled(state);
  }
  this->publish_state(state);
}

void VerifierSwitch::dump_config() { LOG_SWITCH("", "On-device verifier switch", this); }

}  // namespace esphome::micro_wake_word

#endif  // USE_MICRO_WAKE_WORD_VERIFIER
#endif  // USE_ESP32
