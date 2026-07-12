"""Switch platform for micro_wake_word: on-device verifier on/off."""

import esphome.codegen as cg
import esphome.config_validation as cv
import esphome.final_validate as fv
from esphome.components import switch
from esphome.const import CONF_TYPE, ENTITY_CATEGORY_CONFIG

from .. import CONF_MICRO_WAKE_WORD_ID, MicroWakeWord, micro_wake_word_ns

CODEOWNERS = ["@darki73"]

VerifierSwitch = micro_wake_word_ns.class_(
    "VerifierSwitch", switch.Switch, cg.Component
)

TYPE_VERIFIER = "verifier"

CONFIG_SCHEMA = cv.typed_schema(
    {
        TYPE_VERIFIER: switch.switch_schema(
            VerifierSwitch,
            entity_category=ENTITY_CATEGORY_CONFIG,
            default_restore_mode="RESTORE_DEFAULT_ON",
            icon="mdi:shield-check",
        )
        .extend(
            {
                cv.GenerateID(CONF_MICRO_WAKE_WORD_ID): cv.use_id(MicroWakeWord),
            }
        )
        .extend(cv.COMPONENT_SCHEMA),
    },
    default_type=TYPE_VERIFIER,
)


def _require_verifier(config):
    full = fv.full_config.get()
    mww = full.get("micro_wake_word")
    if not mww or "verifier" not in mww:
        raise cv.Invalid(
            "The verifier switch requires micro_wake_word to configure a "
            "`verifier:` model."
        )
    return config


FINAL_VALIDATE_SCHEMA = _require_verifier


async def to_code(config):
    var = await switch.new_switch(config)
    await cg.register_component(var, config)
    await cg.register_parented(var, config[CONF_MICRO_WAKE_WORD_ID])
