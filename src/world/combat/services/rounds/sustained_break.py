"""Breaking a participant's pending sustained actions."""

from __future__ import annotations

from world.combat.models import CombatEncounter, SustainedAction
from world.combat.services.npc.sustained_narration import _broadcast_sustained_broken


def _break_pending_sustained_actions(encounter: CombatEncounter) -> None:
    """Break every still-pending PC ``SustainedAction`` when its encounter ends early.

    Neither ``complete_encounter`` nor this function used to clear
    ``SustainedAction`` rows: an encounter that completes (victory, defeat,
    flee, GM-abandoned) before a commitment's ``resolves_round`` ever arrives
    left the row orphaned forever — it never matures, never narrates, and
    (RITUAL kind) its already-consumed components bought nothing (#2705
    adversarial review, Fix 3). Mirrors the "cost stands" ruling
    ``_mature_one_sustained_action`` applies to a downgrades-exceeded break —
    nothing is refunded here either, only broadcast + delete.

    Called from ``cleanup_completed_encounter``, not ``complete_encounter``
    directly: every production completion path (round-resolution auto-complete,
    the GM end endpoint via ``end_encounter``, duel completion) funnels through
    ``complete_encounter``, which unconditionally calls
    ``cleanup_completed_encounter`` — the same seam that already tears down
    every other encounter-scoped commitment (Audere, engagements, escalation
    triggers, UNTIL_END_OF_COMBAT conditions). Traced, not guessed: the only
    other callers of ``cleanup_completed_encounter`` are tests exercising it in
    isolation.

    ``PendingOpponentAttack`` (the NPC mirror) has the same pre-existing gap —
    deliberately NOT fixed here: out of scope for this issue, and it has no
    consumed-cost consequence (an NPC wind-up never spends anything at
    declaration the way a sustained ritual's components do).
    """
    rows = list(
        SustainedAction.objects.filter(encounter=encounter).select_related(
            "participant__character_sheet__character", "ritual", "technique"
        )
    )
    for sustained in rows:
        _broadcast_sustained_broken(sustained)
        sustained.delete()
