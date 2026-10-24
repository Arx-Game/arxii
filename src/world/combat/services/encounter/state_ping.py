"""Tell every open battle map that a combat encounter changed (#4644).

The battle map reads positions from the REST encounter, polled every 10 seconds.
A round's outcome lines are pushed while the round is still resolving, so a
refetch they trigger can read the encounter from before the round committed. This
ping goes out after the commit instead: a slim ``combat_encounter_state`` message,
the same shape as the battles' ``battle_state`` ping, and the client refetches.

Two writers send it: ``resolve_round`` once per round, and the positioning
primitive's single position writer for any move made outside a resolving round
(a player's move, a GM placement, a forced move).
"""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING

from django.db import transaction

from web.webclient.message_types import CombatEncounterStatePayload
from world.combat.constants import ParticipantStatus
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.combat.models import CombatEncounter


def notify_encounter_changed(encounter: CombatEncounter) -> None:
    """Send the ping to everyone who can have this fight's map open.

    That is everything in the encounter's room (fighters, the GM, bystanders), as the
    room's outcome lines are sent, plus every ACTIVE player character fighting in it
    wherever they stand (an encounter with no room has only these). ``msg`` reaches only
    puppeted sessions, so an object nobody is playing gets nothing.
    """
    payload = asdict(
        CombatEncounterStatePayload(
            encounter_id=encounter.pk,
            round_number=encounter.round_number,
        )
    )
    recipients: dict[int, ObjectDB] = {}
    if encounter.room is not None:
        for obj in encounter.room.contents:
            recipients[obj.pk] = obj
    participants = encounter.participants.filter(status=ParticipantStatus.ACTIVE).select_related(
        "character_sheet__character"
    )
    for participant in participants:
        character = participant.character_sheet.character
        if character is not None:
            recipients[character.pk] = character
    for obj in recipients.values():
        obj.msg(combat_encounter_state=((), payload))


def notify_encounter_changed_on_commit(encounter: CombatEncounter) -> None:
    """Send the ping once the current transaction commits (at once outside one)."""
    transaction.on_commit(lambda: notify_encounter_changed(encounter))


def notify_room_encounters_on_commit(room_id: int | None) -> None:
    """Ping each open encounter in the room after a position change there commits.

    A RESOLVING encounter is skipped: the round sends its own single ping when it
    commits, so the moves inside it do not each send another.
    """
    if room_id is None:
        return
    from world.combat.models import CombatEncounter  # noqa: PLC0415

    encounters = CombatEncounter.objects.filter(room_id=room_id).exclude(
        status__in=[RoundStatus.COMPLETED, RoundStatus.RESOLVING]
    )
    for encounter in encounters:
        notify_encounter_changed_on_commit(encounter)
