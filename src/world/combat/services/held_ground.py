"""Held ground: a ready enemy holds the place it stands in (#4663, slice 2 of #4651).

A player character who enters a place an enemy able to act stands in on the ground stops
there for the round, however she moves (walking, climbing or leaping); her way past is the
pass roll (``held_ground_pass``). One who starts the round there may walk out, and a mover
in the air is not stopped by ground held below; landing in a held place is an entry and
stops her (``LandAction``). ``MoveToPositionAction`` ends a player's movement for the round
on entering a held place. NPCs do not roll: an NPC walker or climber
stops (every NPC route search treats held places as ones it may end in but never walks
through, ``find_path(..., stop_at=...)``) and an NPC flier or leaper passes (``npc_stop_at``).

Outside a live encounter there is no held ground.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from django.db.models import F

from world.areas.positioning.constants import CreatureTraversal
from world.areas.positioning.models import ObjectPosition
from world.areas.positioning.services import position_of
from world.combat.constants import CombatAllegiance, OpponentStatus
from world.combat.models import CombatOpponent, CombatParticipant
from world.combat.services.movement_budget import active_combat_participant
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.combat.models import CombatEncounter
    from world.combat.types import MovementProfile

# Traversals that stop in held ground. A flier passes over it; a leaper bounds past.
_STOPPED_TRAVERSALS = frozenset({CreatureTraversal.WALKS, CreatureTraversal.CLIMBS})


@dataclass(frozen=True)
class EncounterHolds:
    """Where each side's combatants able to act stand in one encounter, read once.

    Built by ``encounter_holds`` once per planning pass (on ``NpcRoundContext``) or once
    per resolution slot, where positions change between slots; every opponent's held set
    is derived from it without another query.
    """

    enemy_opponents: frozenset[int]
    ally_opponents: frozenset[int]
    acting_pcs: frozenset[int]

    def against_opponent(self, opponent: CombatOpponent) -> frozenset[int]:
        """The places held against ``opponent``, by its stored allegiance, its own excluded.

        An ENEMY opponent is held by player characters who can act and by ALLY opponents;
        an ALLY opponent by ENEMY opponents.
        """
        if opponent.allegiance == CombatAllegiance.ALLY:
            held = self.enemy_opponents
        else:
            held = self.acting_pcs | self.ally_opponents
        own = position_of(opponent.objectdb) if opponent.objectdb is not None else None
        return held - {own.pk} if own is not None else held


def encounter_holds(
    encounter: CombatEncounter,
    *,
    acting_participants: list[CombatParticipant] | None = None,
) -> EncounterHolds:
    """Read the encounter's held places: two queries, plus ``can_act`` per participant
    when ``acting_participants`` (the round's PCs who can act) is not handed in.

    ``NpcRoundContext.active_participants`` is that list for a planning pass (PCs who can
    act and are not intangible: an incorporeal or phased PC blocks nobody).
    """
    enemy: set[int] = set()
    ally: set[int] = set()
    for allegiance, position_id in CombatOpponent.objects.filter(
        encounter=encounter,
        status=OpponentStatus.ACTIVE,
        objectdb__object_position__isnull=False,
    ).values_list("allegiance", "objectdb__object_position__position_id"):
        (ally if allegiance == CombatAllegiance.ALLY else enemy).add(position_id)
    if acting_participants is None:
        acting_participants = _acting_participants(encounter)
    sheet_ids = [p.character_sheet_id for p in acting_participants]
    acting = (
        ObjectPosition.objects.filter(objectdb_id__in=sheet_ids).values_list(
            "position_id", flat=True
        )
        if sheet_ids
        else []
    )
    return EncounterHolds(
        enemy_opponents=frozenset(enemy),
        ally_opponents=frozenset(ally),
        acting_pcs=frozenset(acting),
    )


def _acting_participants(encounter: CombatEncounter) -> list[CombatParticipant]:
    """The encounter's PCs who hold ground: ACTIVE, able to act, and not intangible.

    The planning pass's own filter (``npc_targeting._targetable_participants``, the list
    ``NpcRoundContext.active_participants`` carries), so resolution and planning agree.
    """
    from world.combat.services.npc.npc_targeting import (  # noqa: PLC0415
        _targetable_participants,
    )

    return _targetable_participants(encounter)


def enemy_held_places(encounter: CombatEncounter) -> dict[int, list[str]]:
    """Each place a ready enemy holds, by position pk, with who holds it (#4670).

    The places are ``encounter_holds``' enemy set, so a defeated or incapacitated
    opponent holds nothing, and the answer is the same for every viewer. Holder names
    are the opponents' combat names in pk order; two queries (the places, the names).
    """
    places = encounter_holds(encounter, acting_participants=[]).enemy_opponents
    if not places:
        return {}
    held: dict[int, list[str]] = {}
    for position_id, name in (
        CombatOpponent.objects.filter(
            encounter=encounter,
            status=OpponentStatus.ACTIVE,
            allegiance=CombatAllegiance.ENEMY,
            objectdb__object_position__position_id__in=places,
        )
        .annotate(held_position_id=F("objectdb__object_position__position_id"))
        .order_by("pk")
        .values_list("held_position_id", "name")
    ):
        held.setdefault(position_id, []).append(name)
    return held


def held_position_ids_against(
    mover: ObjectDB,  # noqa: OBJECTDB_PARAM - a PC or an NPC's game object
) -> frozenset[int]:
    """The positions an enemy able to act holds against ``mover``, its own excluded.

    For a player character: where her encounter's ACTIVE ENEMY opponents stand. For an
    opponent, ``EncounterHolds.against_opponent``. Empty when the mover is in no live
    encounter.
    """
    participant = active_combat_participant(mover)
    if participant is not None:
        held = set(
            CombatOpponent.objects.filter(
                encounter=participant.encounter,
                status=OpponentStatus.ACTIVE,
                allegiance=CombatAllegiance.ENEMY,
                objectdb__object_position__isnull=False,
            ).values_list("objectdb__object_position__position_id", flat=True)
        )
        own = position_of(mover)
        if own is not None:
            held.discard(own.pk)
        return frozenset(held)
    opponent = (
        CombatOpponent.objects.filter(objectdb=mover, status=OpponentStatus.ACTIVE)
        .exclude(encounter__status=RoundStatus.COMPLETED)
        .select_related("encounter")
        .first()
    )
    if opponent is None:
        return frozenset()
    return encounter_holds(opponent.encounter).against_opponent(opponent)


def npc_stop_at(opponent: CombatOpponent, holds: EncounterHolds | None = None) -> frozenset[int]:
    """The held places an opponent's routes stop in: none for a flier or a leaper.

    ``holds`` is the pass's ``EncounterHolds``; read fresh when not handed in.
    """
    if opponent.objectdb is None:
        return frozenset()
    if opponent.movement_profile.traversal not in _STOPPED_TRAVERSALS:
        return frozenset()
    if holds is None:
        holds = encounter_holds(opponent.encounter)
    return holds.against_opponent(opponent)


def routing_profile(
    opponent: CombatOpponent, holds: EncounterHolds | None = None
) -> MovementProfile:
    """The opponent's movement profile with the held ground its routes stop in.

    Pass the planning pass's ``holds`` so a round's opponents share one read.
    """
    return replace(opponent.movement_profile, stop_at=npc_stop_at(opponent, holds))


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


def held_place_holders(mover: ObjectDB) -> dict[int, str]:  # noqa: OBJECTDB_PARAM - the PC mover
    """Who holds each place held against a player character, by position pk (#4663).

    ``held_position_ids_against`` narrowed to ``holder_names``: the move list's
    "Held by <name>" note and telnet's ``position`` listing both read it. Empty when
    nothing is held against her.
    """
    held = held_position_ids_against(mover)
    if not held:
        return {}
    return {pk: name for pk, name in holder_names(mover).items() if pk in held}
