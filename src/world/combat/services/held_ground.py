"""Held ground: a ready enemy holds the place it stands in (#4663, slice 2 of #4651).

A walker (or climber) who enters a place an enemy able to act stands in stops there for
the round. One who starts the round there may walk out; a flier or a leaper passes over.
Player characters and NPCs obey the same rule: ``MoveToPositionAction`` ends a player's
movement for the round on entering a held place, and every NPC route search treats held
places as ones it may end in but never walks through (``find_path(..., stop_at=...)``).

Outside a live encounter there is no held ground.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from django.db.models import F

from world.areas.positioning.constants import CreatureTraversal
from world.areas.positioning.models import ObjectPosition
from world.areas.positioning.services import position_of
from world.combat.constants import CombatAllegiance, OpponentStatus, ParticipantStatus
from world.combat.models import CombatOpponent, CombatParticipant
from world.combat.services.movement_budget import active_combat_participant
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.combat.models import CombatEncounter
    from world.combat.types import MovementProfile

# Traversals that stop in held ground. A flier passes over it; a leaper bounds past.
_STOPPED_TRAVERSALS = frozenset({CreatureTraversal.WALKS, CreatureTraversal.CLIMBS})


def _live_opponent_row(
    mover: ObjectDB,  # noqa: OBJECTDB_PARAM - an NPC mover has no sheet
) -> CombatOpponent | None:
    """The mover's ACTIVE opponent row in a live encounter, or None."""
    return (
        CombatOpponent.objects.filter(objectdb=mover, status=OpponentStatus.ACTIVE)
        .exclude(encounter__status=RoundStatus.COMPLETED)
        .select_related("encounter")
        .first()
    )


def _opponent_positions(encounter: CombatEncounter, allegiance: str) -> set[int]:
    """Positions of the encounter's ACTIVE opponents of ``allegiance``. One query."""
    return set(
        ObjectPosition.objects.filter(
            objectdb__combat_opponent_rows__encounter=encounter,
            objectdb__combat_opponent_rows__status=OpponentStatus.ACTIVE,
            objectdb__combat_opponent_rows__allegiance=allegiance,
        ).values_list("position_id", flat=True)
    )


def _participant_positions(encounter: CombatEncounter) -> set[int]:
    """Positions of the encounter's ACTIVE participants who can act. One query.

    ``can_act`` reads each sheet's own vitals and awareness; a fight holds a handful of
    player characters.
    """
    from world.vitals.services import can_act  # noqa: PLC0415

    participants = CombatParticipant.objects.filter(
        encounter=encounter, status=ParticipantStatus.ACTIVE
    ).select_related("character_sheet__character__object_position")
    held: set[int] = set()
    for participant in participants:
        sheet = participant.character_sheet
        position = position_of(sheet.character)
        if position is not None and can_act(sheet):
            held.add(position.pk)
    return held


def held_position_ids_against(
    mover: ObjectDB,  # noqa: OBJECTDB_PARAM - a PC or an NPC's game object
) -> frozenset[int]:
    """The positions an enemy able to act holds against ``mover``, its own excluded.

    For a player character: where her encounter's ACTIVE ENEMY opponents stand. For an
    ENEMY opponent: where ACTIVE participants who can act stand, and ACTIVE ALLY
    opponents. For an ALLY opponent: where ACTIVE ENEMY opponents stand. Empty when the
    mover is in no live encounter.
    """
    participant = active_combat_participant(mover)
    if participant is not None:
        held = _opponent_positions(participant.encounter, CombatAllegiance.ENEMY)
    else:
        opponent = _live_opponent_row(mover)
        if opponent is None:
            return frozenset()
        if opponent.allegiance == CombatAllegiance.ALLY:
            held = _opponent_positions(opponent.encounter, CombatAllegiance.ENEMY)
        else:
            held = _participant_positions(opponent.encounter) | _opponent_positions(
                opponent.encounter, CombatAllegiance.ALLY
            )
    own = position_of(mover)
    if own is not None:
        held.discard(own.pk)
    return frozenset(held)


def npc_stop_at(opponent: CombatOpponent) -> frozenset[int]:
    """The held places an opponent's routes stop in: none for a flier or a leaper."""
    if opponent.objectdb is None:
        return frozenset()
    if opponent.movement_profile.traversal not in _STOPPED_TRAVERSALS:
        return frozenset()
    return held_position_ids_against(opponent.objectdb)


def routing_profile(opponent: CombatOpponent) -> MovementProfile:
    """The opponent's movement profile with the held ground its routes stop in, read now."""
    return replace(opponent.movement_profile, stop_at=npc_stop_at(opponent))


def holder_names(mover: ObjectDB) -> dict[int, str]:  # noqa: OBJECTDB_PARAM - the PC mover
    """Who holds each held place against a player character, by position pk. One query.

    The lowest-pk ACTIVE ENEMY opponent standing there, named as the combat log names it.
    Empty when she is in no live encounter.
    """
    participant = active_combat_participant(mover)
    if participant is None:
        return {}
    holders = (
        CombatOpponent.objects.filter(
            encounter=participant.encounter,
            status=OpponentStatus.ACTIVE,
            allegiance=CombatAllegiance.ENEMY,
            objectdb__object_position__isnull=False,
        )
        .annotate(held_position_id=F("objectdb__object_position__position_id"))
        .order_by("-pk")
    )
    # Descending pk, so the lowest pk standing in a place is the last write for it.
    return {holder.held_position_id: holder.name for holder in holders}
