"""Checking boss transitions at round end."""

from __future__ import annotations

from world.combat.constants import OpponentStatus, OpponentTier
from world.combat.models import CombatEncounter, CombatOpponent
from world.combat.services.boss.boss_phase import check_and_advance_boss_phase


def _check_boss_transitions(
    encounter: CombatEncounter,
) -> list[tuple[CombatOpponent, int]]:
    """Check all active bosses for phase transitions, return transitions."""
    transitions: list[tuple[CombatOpponent, int]] = []
    boss_opponents = list(
        CombatOpponent.objects.filter(
            encounter=encounter,
            status=OpponentStatus.ACTIVE,
            tier=OpponentTier.BOSS,
        )
    )
    for boss in boss_opponents:
        boss.refresh_from_db()
        new_phase = check_and_advance_boss_phase(boss)
        if new_phase is not None:
            transitions.append((boss, new_phase.phase_number))
    return transitions
