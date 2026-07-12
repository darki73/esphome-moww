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

### Dropdowns and toggles (native platforms)

The component ships native `switch` and `select` platforms — flash-persisted,
no lambdas (see `test/moww-test.yaml` for a compile-verified example):

```yaml
switch:
  - platform: micro_wake_word
    type: verifier            # on-device verification on/off
    name: "On-device verification"
    # restore_mode: RESTORE_DEFAULT_ON (default)

select:
  - platform: micro_wake_word
    type: sensitivity
    name: "Wake sensitivity"
    # presets: omitted -> Relaxed / Balanced / Paranoid defaults below.
    # Each preset pairs a stage-1 cutoff (applied to every non-internal
    # wake model) with a stage-2 verifier cutoff. Stage 1 stays greedy —
    # it exists to never miss; strictness is the verifier's job.
    # presets:
    #   Relaxed:  { probability_cutoff: 0.10, verifier_cutoff: 0.60 }
    #   Balanced: { probability_cutoff: 0.10, verifier_cutoff: 0.70 }
    #   Paranoid: { probability_cutoff: 0.17, verifier_cutoff: 0.80 }
    # initial_option: Balanced
```

The verifier switch requires a `verifier:` model in `micro_wake_word:` (the
config is rejected otherwise). The select's chosen preset and the switch
state survive reboots via ESP preferences.

### Notes

- Verification runs inline on the inference task (~tens of ms per candidate);
  the audio transport ring buffer is enlarged 120 ms -> 500 ms to absorb it.
- Verification fails open at every step: no verifier, load failure, or
  inference error never eats a detection.
- A refuted candidate is logged at debug level:
  `Verifier refuted 'ева': score 0.12, cutoff 0.70, 43 ms`.
- `pcm_history` keeps the last N seconds of raw audio in PSRAM. It is the
  pre-roll source for stage-3 verification (below).

### Stage 3: verification in Home Assistant (openWakeWord)

openWakeWord never runs on the device — it is far beyond ESP32 budgets. It
runs in Home Assistant as the assist pipeline's wake engine (Wyoming
openWakeWord add-on with your custom model, e.g. `eva_oww`). Stage 3 is how
the device involves it: on a wake-word-triggered pipeline start, the forked
`voice_assistant` component sets the `USE_WAKE_WORD` pipeline flag and
prepends `pcm_history` pre-roll to the audio stream, so HA's wake stage
hears «Ева» itself and verifies it before speech-to-text — same stream, no
extra round trips, no URLs.

```yaml
voice_assistant:
  micro_wake_word: mww          # pre-roll source
  ha_wake_word_verification:
    engine_entity: wake_word.openwakeword   # HA wake engine entity
    pre_roll: 2s

select:
  - platform: micro_wake_word
    type: verification          # Off / On-device / Home Assistant / Both
    name: "Wake verification"
    voice_assistant_id: va
```

Availability is honest: the device subscribes to the engine entity's state.
While it is unavailable (add-on stopped, engine removed), the `Home
Assistant`/`Both` options are refused at selection time, and a
wake-word-triggered start falls back to passing through rather than handing
the detection to a wake stage that would never answer. HA-side requirements:
the device's assist pipeline must have the openWakeWord engine with your
wake model selected as its wake word.

### Model contracts

The component loads two streaming-model formats, detected automatically from
the flatbuffer:

- **v1** (kahrendt/microWakeWord): streaming state lives in TFLite resource
  variables inside the model (`VAR_HANDLE`/`READ_VARIABLE`/... ops). All
  published models, including the Voice PE `stop` timer model, keep working.
- **v2** (wakegen-native): state is explicit input/output tensor pairs —
  `output_0` is the probability, output *i+1* pairs with the *i*-th state
  input. The component validates each pair's dims and quantization at load,
  initializes states to their quantized zero point, and feeds the raw int8
  bytes back after every invoke (quantization parity makes that lossless).
  v2 models need no resource-variable arena and no CallOnce/VarHandle ops.

Detection rule: more than one subgraph input = v2. Everything above the
loader (cutoffs, sliding window, verifier cascade, HA integration) is
contract-agnostic.

## Provenance & license

`components/micro_wake_word/` derives from ESPHome's `micro_wake_word` component
(baseline: ESPHome 2026.6.5, commit `3bfbaaebf`). ESPHome C++ sources are
GPLv3-licensed; this repository therefore is distributed under GPLv3 as well.

The baseline is committed pristine before any modification — `git log` on the
component directory shows the exact divergence from upstream.
