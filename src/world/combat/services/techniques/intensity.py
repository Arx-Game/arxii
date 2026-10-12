"""Effective intensity for a technique or clash."""

from __future__ import annotations

from world.combat.models import CombatEncounter, CombatParticipant, CombatRoundAction
from world.magic.constants import EffectKind


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
