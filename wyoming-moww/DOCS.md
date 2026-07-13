# Wyoming moww

Runs moww wake word models (the same streaming detector + one-shot verifier
cascade the esphome-moww firmware runs on-device) as a Wyoming wake engine
for Assist pipelines.

## Setup

1. Copy your model pair to `/share/moww/` on Home Assistant:
   - `<name>.tflite` — streaming contract-v2 detector (required)
   - `<name>_verifier.tflite` — one-shot verifier (strongly recommended)
   - `<name>.json` — model manifest; its `wake_word` field is shown as the
     phrase in the UI
2. Start the add-on. The Wyoming integration discovers it automatically.
   To add it manually instead: Settings → Devices & services → Add
   integration → Wyoming Protocol, host `localhost` (or the HA machine's
   IP), port `10400`.
3. In your Assist pipeline settings, pick the moww wake word.

## Options

| Option | Default | Meaning |
| --- | --- | --- |
| `models_dir` | `/share/moww` | Directory scanned for model pairs |
| `stage1_cutoff` | `0.10` | Streaming detector cutoff (greedy on purpose — its job is to never miss; strictness belongs to the verifier) |
| `verifier_cutoff` | `0.15` | One-shot verifier cutoff |
| `verifier` | `true` | Disable to run stage 1 only (not recommended) |
| `debug` | `false` | Per-candidate verifier logging |

The defaults match the firmware's measured "Balanced" preset.
