# esphome-moww

Multi-stage wake word verification for ESPHome — a drop-in enhanced fork of the
`micro_wake_word` component that adds a wake word verification cascade:

- **Stage 1 — streaming detector** (stock microWakeWord behavior) run at a
  recall-greedy cutoff: its job is to never miss.
- **Stage 2 — on-device one-shot verifier**: a non-streaming variant of the same
  model re-scores the whole utterance window (~50 ms, no network) and kills most
  false candidates locally.
- **Stage 3 — Home Assistant verification** *(planned)*: the assist pipeline is
  started at the wake-word stage with buffered pre-roll audio, so a server-side
  openWakeWord model gets the final say and the same stream continues straight
  into STT on confirmation.

All stages are opt-in: without a `verifier:` block the component compiles and
behaves identically to stock `micro_wake_word`.

## Usage

```yaml
external_components:
  - source: github://darki73/esphome-moww
    components: [micro_wake_word]
    refresh: 0s

micro_wake_word:
  id: mww
  microphone: ...
  models:
    - model: <manifest url>
      id: eva
  pcm_history:
    duration: 3s          # PSRAM ring of raw audio (stage 0 / stage 3 pre-roll)
  verifier:
    model: <non-streaming tflite url>
    probability_cutoff: 0.7
```

Because the component keeps the upstream name, the stock `voice_assistant`
integration, `micro_wake_word.*` actions, and Home Assistant wake word selection
keep working unchanged.

### Voice PE overlay

For an adopted Home Assistant Voice PE config (package-based), the whole
cascade is this overlay — the component override shadows the bundled one and
`!extend` adds the new blocks to the existing `mww` instance:

```yaml
external_components:
  - source: github://darki73/esphome-moww
    components: [micro_wake_word]
    refresh: 0s

micro_wake_word:
  id: !extend mww
  pcm_history:
  verifier:
    model: http://<ha-host>:8123/local/mww/eva_verifier.tflite
    probability_cutoff: 0.7
```

The verifier model is downloaded at **build** time and embedded in the
firmware, like the wake models themselves. Without the `verifier:` block the
firmware is behaviorally identical to stock (verified: both variants compile;
the cascade code is fully `#ifdef`-gated).

### Dropdowns and toggles (interim, via template entities)

Native sub-platform entities are planned for the stage-3 phase. Until then the
runtime API is fully controllable from template entities, the same pattern the
stock Voice PE firmware uses for its sensitivity select
(see `test/moww-test.yaml` for a compile-verified example):

```yaml
switch:
  - platform: template
    name: "On-device verification"
    optimistic: true
    restore_mode: RESTORE_DEFAULT_ON
    turn_on_action:
      - lambda: id(mww).get_verifier_model()->set_enabled(true);
    turn_off_action:
      - lambda: id(mww).get_verifier_model()->set_enabled(false);

select:
  - platform: template
    name: "Wake sensitivity"
    optimistic: true
    initial_option: "Balanced"
    restore_value: true
    entity_category: config
    options: [Relaxed, Balanced, Paranoid]
    on_value:
      # Strictness is mostly the verifier's job; stage 1 stays greedy.
      # Cutoffs are quantized: value = round(probability * 255).
      lambda: |-
        if (x == "Relaxed") {
          id(my_wake_word).set_probability_cutoff(26);                 // stage-1 0.10
          id(mww).get_verifier_model()->set_probability_cutoff(153);  // stage-2 0.60
        } else if (x == "Balanced") {
          id(my_wake_word).set_probability_cutoff(26);
          id(mww).get_verifier_model()->set_probability_cutoff(178);  // 0.70
        } else {
          id(my_wake_word).set_probability_cutoff(43);                 // stage-1 0.17
          id(mww).get_verifier_model()->set_probability_cutoff(204);  // 0.80
        }
```

### Notes

- Verification runs inline on the inference task (~tens of ms per candidate);
  the audio transport ring buffer is enlarged 120 ms -> 500 ms to absorb it.
- Verification fails open at every step: no verifier, load failure, or
  inference error never eats a detection.
- A refuted candidate is logged at debug level:
  `Verifier refuted 'ева': score 0.12, cutoff 0.70, 43 ms`.
- `pcm_history` keeps the last N seconds of raw audio in PSRAM. It is not yet
  consumed by anything; it is the pre-roll source for the upcoming
  pipeline-native Home Assistant verification stage (stage 3).

## Provenance & license

`components/micro_wake_word/` derives from ESPHome's `micro_wake_word` component
(baseline: ESPHome 2026.6.5, commit `3bfbaaebf`). ESPHome C++ sources are
GPLv3-licensed; this repository therefore is distributed under GPLv3 as well.

The baseline is committed pristine before any modification — `git log` on the
component directory shows the exact divergence from upstream.
