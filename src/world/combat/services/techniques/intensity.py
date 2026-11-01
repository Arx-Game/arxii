"""Effective intensity for a technique or clash."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.models import CombatEncounter, CombatParticipant, CombatRoundAction
from world.magic.constants import EffectKind

if TYPE_CHECKING:
    from world.checks.types import ModifierContribution


def _sum_active_flat_bonuses(
    participant: CombatParticipant,
    encounter: CombatEncounter,
) -> int:
    """Sum scaled_value across FLAT_BONUS resolved-effect rows on the
    participant's active CombatPull rows for this encounter.

    Reads through CharacterCombatPullHandler so the cached/prefetched
    list is honored — avoids re-querying.
    """
    character = participant.character_sheet.character
    total = 0
    for pull in character.combat_pulls.active_for_encounter(encounter):
        for eff in pull.resolved_effects_cached:
            if eff.kind == EffectKind.FLAT_BONUS and eff.scaled_value:
                total += eff.scaled_value
    return total


def compute_intensity_for_clash(
    participant: CombatParticipant,
    action: CombatRoundAction,
) -> int:
    """Return technique.intensity + active INTENSITY_BUMP pull bonuses for the clash floor gate.

    Used exclusively to gate the clash-open check (intensity_floor). Future
    intensity-ramp contributions (conditions, items, environment) can be added
    here and they will tighten the floor automatically.
    """
    technique = action.focused_action
    if technique is None:
        return 0
    base = technique.intensity
    encounter = participant.encounter
    pull_bonus = 0
    character = participant.character_sheet.character
    for pull in character.combat_pulls.active_for_encounter(encounter):
        for eff in pull.resolved_effects_cached:
            if eff.kind == EffectKind.INTENSITY_BUMP and eff.scaled_value:
                pull_bonus += eff.scaled_value
    return base + pull_bonus


# ---------------------------------------------------------------------------
# Misses build intensity, and intensity adds to hit (#4858)
# ---------------------------------------------------------------------------


def intensity_to_hit_contribution(participant: CombatParticipant) -> ModifierContribution | None:
    """What the attacker's engagement intensity adds to an attack roll, or None.

    Each point of ``intensity_modifier`` on her engagement (whatever its type, the one the
    Pressure card shows) adds "Intensity: to hit per point" (the maneuver effect catalog:
    its base plus modifiers scoped to that effect alone; a broad to-hit modifier is a flat
    bonus, not a rate). Nothing at 0 or below. Read on every attack roll, technique or
    Strike.
    """
    from world.checks.constants import ModifierSourceKind  # noqa: PLC0415
    from world.checks.types import ModifierContribution  # noqa: PLC0415
    from world.combat.services.encounter.engagement import (  # noqa: PLC0415
        engagement_of_any_type_for,
    )
    from world.mechanics.constants import ManeuverEffectKey  # noqa: PLC0415
    from world.mechanics.effect_targets import effect_modifier_total  # noqa: PLC0415
    from world.mechanics.maneuver_effects import get_maneuver_effect  # noqa: PLC0415

    engagement = engagement_of_any_type_for(participant.character_sheet.character)
    intensity = engagement.intensity_modifier if engagement is not None else 0
    if intensity <= 0:
        return None
    key = ManeuverEffectKey.INTENSITY_TO_HIT
    per_point = max(
        0,
        get_maneuver_effect(key).base_value
        + effect_modifier_total(participant.character_sheet, key, kind_wide=False),
    )
    if per_point <= 0:
        return None
    return ModifierContribution(
        source_kind=ModifierSourceKind.CHARACTER,
        source_label="Intensity",
        value=intensity * per_point,
    )


def is_miss(success_level: int | None) -> bool:
    """Whether an attack roll at ``success_level`` missed: it would deal no damage."""
    from world.conditions.services import get_damage_multiplier  # noqa: PLC0415

    return get_damage_multiplier(success_level or 0) <= 0


def record_miss_intensity(participant: CombatParticipant) -> None:
    """A missed attack raises the attacker's intensity (#4858), once a round.

    The amount is "Miss: intensity gained" (the maneuver effect catalog, with her
    modifiers). Written through ``apply_dramatic_surge``, the one intensity seam: a MISSED
    surge for this round, with no room line. Nothing without a combat engagement here.
    """
    from world.combat.constants import SurgeTriggerKind  # noqa: PLC0415
    from world.combat.escalation import apply_dramatic_surge  # noqa: PLC0415
    from world.mechanics.constants import ManeuverEffectKey  # noqa: PLC0415
    from world.mechanics.effect_targets import effect_value  # noqa: PLC0415

    amount = effect_value(participant.character_sheet, ManeuverEffectKey.MISS_INTENSITY)
    if amount <= 0:
        return
    encounter = participant.encounter
    apply_dramatic_surge(
        encounter=encounter,
        participant=participant,
        amount=amount,
        trigger_kind=SurgeTriggerKind.MISSED,
        repeat_round=encounter.round_number,
        narrate=False,
        cause="A missed attack.",
    )
