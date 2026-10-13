"""Conditions that interact with incoming damage."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.constants import ENEMY_LANE_CAP_PERCENT

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.conditions.models import DamageType
    from world.conditions.types import DamageInteractionResult


def _apply_condition_damage_interactions(
    target: ObjectDB,  # noqa: OBJECTDB_PARAM
    damage_type: DamageType | None,
    damage_amount: int,
) -> tuple[int, DamageInteractionResult | None]:
    """Run condition-damage interactions on a target, returning modified damage + result.

    Called from both combat damage paths after soak/resistance/armor (#2018).
    The interaction modifier is a final percentage multiplier on net damage — SUMMED
    across every matching ``ConditionDamageInteraction`` row, then clamped to
    ``±ENEMY_LANE_CAP_PERCENT`` (#2643, Undermine's enemy-side lane; the same EQ2 lane
    guard as the team-damage-percent lane — see ``world.magic.constants
    .TEAM_BUFF_LANE_CAP_PERCENT``). The clamp applies to the summed percent, not to any
    individual authored row — an authored row may itself exceed the band; only the
    live total a target can accumulate is bounded.
    Returns ``(modified_damage, interaction_result)`` — ``interaction_result``
    is None when damage_type is None, a non-model value, or damage_amount is zero.
    """
    if damage_type is None or damage_amount <= 0:
        return damage_amount, None
    # Some callers pass a string damage_type (e.g. "physical") rather than a
    # DamageType model instance. Condition-damage interactions require a real
    # model to query the interaction table — skip for non-model values.
    from world.conditions.models import DamageType  # noqa: PLC0415

    if not isinstance(damage_type, DamageType):
        return damage_amount, None
    from world.conditions.services import process_damage_interactions  # noqa: PLC0415

    result = process_damage_interactions(target, damage_type)
    if result.damage_modifier_percent != 0:
        clamped_percent = max(
            -ENEMY_LANE_CAP_PERCENT, min(ENEMY_LANE_CAP_PERCENT, result.damage_modifier_percent)
        )
        damage_amount = max(0, int(damage_amount * (1 + clamped_percent / 100)))
    return damage_amount, result
