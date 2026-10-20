"""Save rules for trial consequences (#4501, spec #4343 section 6).

A *trial* is a mission whose good outcome tiers make a codex entry known, train or grant
the technique that entry opens, and cost the character something. There is no trial model:
the rules live here, over ``Consequence`` and ``ConsequenceEffect``, so every authoring
surface refuses the same things. ``ConsequenceEffect.clean`` runs ``effect_trial_errors``
(one effect against its consequence's tier). The inline effect formset and the Trial builder
(slice 2) run ``consequence_trial_errors`` over the whole proposed effect set, because the
cost rule needs the sibling effects and a form saves those after the consequence's own
``clean``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist

from world.checks.constants import (
    CRITICAL_SUCCESS_TIER_MIN_LEVEL,
    FAILURE_TIER_MAX_LEVEL,
    SUCCESS_TIER_MIN_LEVEL,
    EffectTarget,
    EffectType,
)

if TYPE_CHECKING:
    from world.checks.models import Consequence, ConsequenceEffect


def _tier_level(effect: ConsequenceEffect) -> int | None:
    """The ``success_level`` of the effect's consequence tier, or None when unattached."""
    try:
        consequence = effect.consequence
    except ObjectDoesNotExist:
        return None
    if consequence.outcome_tier_id is None:
        return None
    return consequence.outcome_tier.success_level


def effect_gates_technique(effect: ConsequenceEffect) -> bool:
    """True when a GRANT_CODEX effect names an entry some technique requires."""
    if effect.effect_type != EffectType.GRANT_CODEX or effect.codex_entry_id is None:
        return False
    from world.codex.services import entry_gates_technique  # noqa: PLC0415

    return entry_gates_technique(effect.codex_entry)


def _grants_known_errors(effect: ConsequenceEffect, level: int | None) -> dict[str, str]:
    errors: dict[str, str] = {}
    if effect.grants_known:
        if effect.effect_type != EffectType.GRANT_CODEX:
            errors["grants_known"] = "grants_known applies only to GRANT_CODEX effects."
        elif level is not None and level < SUCCESS_TIER_MIN_LEVEL:
            errors["grants_known"] = "An entry is made known only at Success or Critical Success."
    if (
        effect.effect_type == EffectType.GRANT_CODEX
        and level is not None
        and level <= FAILURE_TIER_MAX_LEVEL
        and effect_gates_technique(effect)
    ):
        errors["codex_entry"] = (
            "This entry gates a technique; it may not be granted on a Failure, known or uncovered."
        )
    return errors


def _cosmetic_scar_errors(effect: ConsequenceEffect, level: int | None) -> dict[str, str]:
    if not effect.scar_is_cosmetic:
        return {}
    if effect.effect_type != EffectType.MAGICAL_SCARS:
        return {"scar_is_cosmetic": "scar_is_cosmetic applies only to MAGICAL_SCARS effects."}
    if level is not None and level < SUCCESS_TIER_MIN_LEVEL:
        return {"scar_is_cosmetic": "A cosmetic Mage Scar is a reward for Success or better."}
    return {}


def _training_errors(effect: ConsequenceEffect, level: int | None) -> dict[str, str]:
    errors: dict[str, str] = {}
    carries_training_field = bool(
        effect.technique_id
        or effect.training_points
        or effect.training_meter_size
        or effect.grants_technique_outright
    )
    if effect.effect_type != EffectType.TECHNIQUE_TRAINING:
        if carries_training_field:
            errors["technique"] = "Training fields apply only to TECHNIQUE_TRAINING effects."
        return errors
    if level is not None and level <= FAILURE_TIER_MAX_LEVEL:
        errors["effect_type"] = "Technique training is not allowed on a Failure."
    if effect.technique_id and effect.technique.is_ultimate:
        errors["technique"] = "An ultimate is reached only at Audere; a trial cannot train it."
    if not effect.grants_technique_outright and not effect.training_points:
        errors["training_points"] = "Give training points, or tick grant outright."
    if effect.grants_technique_outright and (
        level is not None and level < CRITICAL_SUCCESS_TIER_MIN_LEVEL
    ):
        errors["grants_technique_outright"] = "Granting outright is for Critical Success only."
    if (
        effect.training_points
        and not effect.grants_technique_outright
        and not effect.training_meter_size
    ):
        errors["training_meter_size"] = (
            "A character with no meter yet gets one of this size; give the size."
        )
    return errors


def effect_trial_errors(effect: ConsequenceEffect) -> dict[str, str]:
    """Field errors for one effect against its consequence's tier (#4501)."""
    level = _tier_level(effect)
    return {
        **_grants_known_errors(effect, level),
        **_cosmetic_scar_errors(effect, level),
        **_training_errors(effect, level),
    }


def is_cost_effect(effect: ConsequenceEffect) -> bool:
    """A real cost: a non-cosmetic Mage Scar or a condition, on the actor."""
    if effect.target != EffectTarget.SELF:
        return False
    if effect.effect_type == EffectType.MAGICAL_SCARS:
        return not effect.scar_is_cosmetic
    return effect.effect_type == EffectType.APPLY_CONDITION


def is_opening_effect(effect: ConsequenceEffect) -> bool:
    """Makes known an entry that gates a technique, or trains a technique."""
    if effect.effect_type == EffectType.TECHNIQUE_TRAINING:
        return True
    return bool(effect.grants_known) and effect_gates_technique(effect)


def consequence_trial_errors(
    consequence: Consequence,
    effects: Sequence[ConsequenceEffect],
) -> list[str]:
    """Whole-set errors for a consequence and its proposed effects (#4501).

    - a consequence that opens a technique carries a real cost, unless it is deliberately
      free with a reason; a cosmetic Mage Scar is a reward and never the cost;
    - training runs after the codex effect that makes the entry known.
    """
    errors: list[str] = []
    opening = [e for e in effects if is_opening_effect(e)]
    if opening and not any(is_cost_effect(e) for e in effects):
        free_ok = consequence.deliberately_free and consequence.free_reason.strip()
        if not free_ok:
            only_cosmetic = any(
                e.effect_type == EffectType.MAGICAL_SCARS and e.scar_is_cosmetic for e in effects
            )
            errors.append(
                "This consequence opens or trains a technique and has no cost."
                + (" A cosmetic Mage Scar is a reward, not a cost." if only_cosmetic else "")
                + " Add a Mage Scar or a condition on the actor, or mark it deliberately free"
                " with a reason."
            )
    known_orders = [
        e.execution_order
        for e in effects
        if e.effect_type == EffectType.GRANT_CODEX and e.grants_known
    ]
    for effect in effects:
        if effect.effect_type == EffectType.TECHNIQUE_TRAINING and any(
            order >= effect.execution_order for order in known_orders
        ):
            errors.append(
                "Technique training must run after the codex effect that makes the entry "
                "known (a higher execution order)."
            )
            break
    return errors
