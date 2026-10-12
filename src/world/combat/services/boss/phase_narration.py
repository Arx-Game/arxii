"""Narration for a boss phase transition."""

from __future__ import annotations

from world.combat.constants import ENRAGE_NARRATION, PHASE_SHIFT_NARRATION
from world.combat.models import BossPhase, CombatOpponent
from world.combat.services.npc.narration import _dual_dispatch_combat_narration


def _narrate_phase_transition(
    opponent: CombatOpponent,
    phase: BossPhase,
    *,
    enraged: bool,
) -> None:
    """Tell the room a boss just changed phase (#3552).

    The dramatic surge for the same transition is generic (ADR-0098 never names
    the subject) and curve-gated, so until now a phase change was invisible at
    the table. ``BossPhase.description`` is authored per phase for exactly this
    moment (copied from ``CreaturePhaseTemplate`` at spawn) and had no reader.
    Dual-dispatched so telnet sees the same line.
    """
    line = phase.description.strip() or PHASE_SHIFT_NARRATION.format(name=opponent.name)
    _dual_dispatch_combat_narration(opponent.encounter, line)
    if enraged:
        _dual_dispatch_combat_narration(
            opponent.encounter, ENRAGE_NARRATION.format(name=opponent.name)
        )
