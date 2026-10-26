"""Place-covering NPC attacks: everyone in the place is hit, leaving it escapes (#4676)."""

from __future__ import annotations

from world.areas.positioning.models import Position
from world.areas.positioning.services import position_of
from world.combat.constants import ParticipantStatus
from world.combat.models import CombatOpponentAction, CombatParticipant


def place_of_participant(participant: CombatParticipant | None) -> Position | None:
    """Where this participant's character stands, or None."""
    if participant is None:
        return None
    return position_of(participant.character_sheet.character)


def cover_place(npc_action: CombatOpponentAction) -> None:
    """Point a place-covering attack at everyone standing in its place now.

    The place is the one its wind-up was telegraphed on, else its first target's place
    as it resolves; it is stored on the action so every target's dodge reads the same
    place. Whoever walked out on her turn is no longer a target; whoever walked in is.
    No-op for any other attack.
    """
    if not npc_action.threat_entry.covers_place:
        return
    place = npc_action.covered_position
    if place is None:
        first = npc_action.targets.select_related("character_sheet__character").first()
        place = place_of_participant(first)
        if place is None:
            return
        npc_action.covered_position = place
        npc_action.save(update_fields=["covered_position"])
    occupants = list(
        CombatParticipant.objects.filter(
            encounter=npc_action.opponent.encounter,
            status=ParticipantStatus.ACTIVE,
            character_sheet__character__object_position__position=place,
        ).select_related("character_sheet__character")
    )
    npc_action.targets.set(occupants)
    # The M2M changed under any prefetched list; drop it so resolution re-reads.
    npc_action.__dict__.pop("cached_targets", None)
