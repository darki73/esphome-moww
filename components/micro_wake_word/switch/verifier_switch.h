#pragma once

#ifdef USE_ESP32

#include "../micro_wake_word.h"

#ifdef USE_MICRO_WAKE_WORD_VERIFIER

#include "esphome/components/switch/switch.h"
#include "esphome/core/component.h"

namespace esphome::micro_wake_word {

/// Exposes the on-device verifier (stage 2) as a switch. Turning it off
/// makes candidate detections pass straight through, exactly as if no
/// verifier model were configured. State persists via the standard switch
/// restore modes.
class VerifierSwitch : public switch_::Switch, public Component, public Parented<MicroWakeWord> {
 public:
  void setup() override;
  void dump_config() override;

 protected:
  void write_state(bool state) override;
};

}  // namespace esphome::micro_wake_word

#endif  // USE_MICRO_WAKE_WORD_VERIFIER
#endif  // USE_ESP32
