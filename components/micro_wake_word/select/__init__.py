"""Select platform for micro_wake_word: sensitivity presets.

Each preset pairs a stage-1 streaming cutoff (applied to every non-internal
wake word model) with a stage-2 verifier cutoff. The active preset persists
in flash.
"""

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import select
from esphome.const import CONF_TYPE, ENTITY_CATEGORY_CONFIG

from .. import (
    CONF_MICRO_WAKE_WORD_ID,
    CONF_PROBABILITY_CUTOFF,
    MicroWakeWord,
    micro_wake_word_ns,
)

CODEOWNERS = ["@darki73"]

SensitivitySelect = micro_wake_word_ns.class_(
    "SensitivitySelect", select.Select, cg.Component
)

TYPE_SENSITIVITY = "sensitivity"

CONF_PRESETS = "presets"
CONF_VERIFIER_CUTOFF = "verifier_cutoff"
CONF_INITIAL_OPTION = "initial_option"

_PRESET_SCHEMA = cv.Schema(
    {
        cv.Required(CONF_PROBABILITY_CUTOFF): cv.percentage,
        cv.Optional(CONF_VERIFIER_CUTOFF, default=0.7): cv.percentage,
    }
)

# Cutoffs from the eva fleet tuning: stage 1 stays greedy (it exists to
# never miss), strictness is the verifier's job.
_DEFAULT_PRESETS = {
    "Relaxed": {CONF_PROBABILITY_CUTOFF: 0.10, CONF_VERIFIER_CUTOFF: 0.60},
    "Balanced": {CONF_PROBABILITY_CUTOFF: 0.10, CONF_VERIFIER_CUTOFF: 0.70},
    "Paranoid": {CONF_PROBABILITY_CUTOFF: 0.17, CONF_VERIFIER_CUTOFF: 0.80},
}


def _validate_initial(config):
    if config[CONF_INITIAL_OPTION] not in config[CONF_PRESETS]:
        raise cv.Invalid(
            f"initial_option '{config[CONF_INITIAL_OPTION]}' is not a preset "
            f"(have: {', '.join(config[CONF_PRESETS])})"
        )
    return config


CONFIG_SCHEMA = cv.All(
    cv.typed_schema(
        {
            TYPE_SENSITIVITY: select.select_schema(
                SensitivitySelect,
                entity_category=ENTITY_CATEGORY_CONFIG,
                icon="mdi:tune-vertical",
            )
            .extend(
                {
                    cv.GenerateID(CONF_MICRO_WAKE_WORD_ID): cv.use_id(MicroWakeWord),
                    cv.Optional(CONF_PRESETS, default=_DEFAULT_PRESETS): cv.Schema(
                        {cv.string_strict: _PRESET_SCHEMA}
                    ),
                    cv.Optional(CONF_INITIAL_OPTION, default="Balanced"): cv.string_strict,
                }
            )
            .extend(cv.COMPONENT_SCHEMA),
        },
        default_type=TYPE_SENSITIVITY,
    ),
    _validate_initial,
)


def _quantized(cutoff: float) -> int:
    return min(int(cutoff * 255), 255)


async def to_code(config):
    options = list(config[CONF_PRESETS])
    var = await select.new_select(config, options=options)
    await cg.register_component(var, config)
    await cg.register_parented(var, config[CONF_MICRO_WAKE_WORD_ID])
    for preset in config[CONF_PRESETS].values():
        cg.add(
            var.add_preset(
                _quantized(preset[CONF_PROBABILITY_CUTOFF]),
                _quantized(preset[CONF_VERIFIER_CUTOFF]),
            )
        )
    cg.add(var.set_initial_index(options.index(config[CONF_INITIAL_OPTION])))
