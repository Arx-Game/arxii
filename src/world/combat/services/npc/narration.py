"""Narration for commitments and the shared dispatch."""

from __future__ import annotations

from world.combat.models import CombatEncounter


def _dual_dispatch_combat_narration(encounter: CombatEncounter, narration: str) -> None:
    """Broadcast a combat narration line to BOTH clients (HARD telnet parity).

    Mirrors ``world.covenants.perks.services.announce_fired_perks``'s
    dual-dispatch shape: a persisted, Narrator-authored OUTCOME Interaction
    over the WS interaction payload
    (``world.combat.interaction_services.broadcast_action_outcome``) PLUS a
    direct ``room.msg_contents(narration)`` text companion so bare telnet
    clients render the identical line — ``broadcast_action_outcome`` alone is
    WS-only.
    """
    from world.combat.interaction_services import broadcast_action_outcome  # noqa: PLC0415

    broadcast_action_outcome(encounter=encounter, narration=narration)
    room = encounter.room
    if room is not None:
        room.msg_contents(narration)


def _broadcast_commitment_line(encounter: CombatEncounter, narration: str) -> None:
    """Shared dispatch core for either side's multi-round commitment (#2637 NPC, #2705 PC).

    ``PendingOpponentAttack`` (NPC wind-up) and ``SustainedAction`` (PC sustain)
    each narrate from a different subject — an ``opponent.name`` vs a
    participant's character name plus ``sustained.subject_name`` — so a single
    row-polymorphic helper would just branch on type at every call. What both
    rows genuinely share is the *dispatch*: one narration line, broadcast to
    both the WS interaction payload and the telnet room. That is the only
    thing this function generalises; every ``_broadcast_windup_*`` /
    ``_broadcast_sustained_*`` wrapper below builds its own narration text and
    calls this once.
    """
    _dual_dispatch_combat_narration(encounter, narration)
