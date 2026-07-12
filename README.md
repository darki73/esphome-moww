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

## Provenance & license

`components/micro_wake_word/` derives from ESPHome's `micro_wake_word` component
(baseline: ESPHome 2026.6.5, commit `3bfbaaebf`). ESPHome C++ sources are
GPLv3-licensed; this repository therefore is distributed under GPLv3 as well.

The baseline is committed pristine before any modification — `git log` on the
component directory shows the exact divergence from upstream.
