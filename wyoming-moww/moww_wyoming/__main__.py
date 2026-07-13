"""wyoming-moww entrypoint.

Discovers moww model pairs in --models-dir:
  <name>.tflite            streaming contract-v2 detector (required)
  <name>_verifier.tflite   one-shot verifier (optional but recommended)
  <name>.json              manifest; wake_word field becomes the phrase
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from functools import partial
from pathlib import Path

from wyoming.info import Attribution, Info, WakeModel as WyomingWakeModel, WakeProgram
from wyoming.server import AsyncServer

from . import __version__
from .engine import WakeModel
from .handler import MowwEventHandler

_LOGGER = logging.getLogger(__name__)


def discover_models(
    models_dir: Path, stage1_cutoff: float, verifier_cutoff: float, verifier: bool
) -> dict[str, WakeModel]:
    models: dict[str, WakeModel] = {}
    for streaming_path in sorted(models_dir.glob("*.tflite")):
        if streaming_path.stem.endswith("_verifier"):
            continue
        verifier_path = streaming_path.with_name(
            f"{streaming_path.stem}_verifier.tflite"
        )
        try:
            model = WakeModel.load(
                streaming_path,
                verifier_path if (verifier and verifier_path.is_file()) else None,
                stage1_cutoff,
                verifier_cutoff,
            )
        except Exception:
            _LOGGER.exception(
                "Skipping %s: not a loadable moww model", streaming_path.name
            )
            continue
        models[model.name] = model
    return models


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--uri", default="tcp://0.0.0.0:10400")
    parser.add_argument("--models-dir", type=Path, default=Path("/share/moww"))
    # Defaults match the firmware's measured "Balanced" preset
    parser.add_argument("--stage1-cutoff", type=float, default=0.10)
    parser.add_argument("--verifier-cutoff", type=float, default=0.15)
    parser.add_argument(
        "--no-verifier", action="store_true", help="Stage 1 only (not recommended)"
    )
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    if not args.models_dir.is_dir():
        raise SystemExit(f"Models directory not found: {args.models_dir}")
    models = discover_models(
        args.models_dir,
        args.stage1_cutoff,
        args.verifier_cutoff,
        verifier=not args.no_verifier,
    )
    if not models:
        raise SystemExit(
            f"No .tflite models in {args.models_dir}. Copy the moww pair "
            "(<name>.tflite + <name>_verifier.tflite) there."
        )

    wyoming_info = Info(
        wake=[
            WakeProgram(
                name="moww",
                description="Multi-stage wake word (streaming detector + verifier)",
                attribution=Attribution(
                    name="darki73",
                    url="https://github.com/darki73/esphome-moww",
                ),
                installed=True,
                version=__version__,
                models=[_wyoming_model(model) for model in models.values()],
            )
        ]
    )

    server = AsyncServer.from_uri(args.uri)
    _LOGGER.info(
        "wyoming-moww %s: %d model(s) at %s", __version__, len(models), args.uri
    )
    await server.run(partial(MowwEventHandler, wyoming_info, models))


def _wyoming_model(model: WakeModel) -> WyomingWakeModel:
    return WyomingWakeModel(
        name=model.name,
        description=model.phrase,
        phrase=model.phrase,
        attribution=Attribution(
            name="darki73", url="https://github.com/darki73/esphome-moww"
        ),
        installed=True,
        languages=[],
        version=None,
    )


if __name__ == "__main__":
    asyncio.run(main())
