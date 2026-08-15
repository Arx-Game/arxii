"""Doorman announcement service (#2989).

Ships as **announcement only** — a deterministic room echo naming every
arrival, no check roll, mirroring the ward/alarm "deterministic reaction"
precedent (``world.room_features.services.react_to_unauthorized_entry``).
"Turning away the unwanted" (an access challenge) is deferred: it needs a
real invitation/guest-list authorization primitive that doesn't exist yet —
a separate, larger design question, not a small behavior-authoring add. The
unresistable expulsion valve (``world.npc_services.expulsion_services``)
covers the "get rid of a disruptive character" need in the meantime.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.npc_services.models import AssignmentRole, NPCAssignment

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


def announce_arrival(character: ObjectDB, room: ObjectDB) -> None:
    """Announce ``character``'s arrival in ``room`` if a DOORMAN is posted.

    Called from ``Character.at_post_move``, alongside ``check_guard_detection``,
    on EVERY character movement anywhere — so the no-doorman case (the
    overwhelming majority of rooms/moves) must create nothing and cost the
    fewest possible queries. Reads the room's ``RoomProfile`` with a plain
    ``filter().first()`` rather than ``world.areas.services.get_room_profile``
    (which ``get_or_create``s — a write this hot path must never trigger just
    to check whether a doorman is posted). Short-circuits (one read query,
    zero writes) when the room has no profile or no active DOORMAN
    assignment. The arriving character is excluded from the room echo — they
    know they arrived. No check, no gate on owner/tenant standing: the
    doorman announces everyone (per the ratified #2989 amendments).
    """
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415

    profile = RoomProfile.objects.filter(objectdb=room).first()
    if profile is None:
        return

    doorman = (
        NPCAssignment.objects.filter(
            room=profile,
            assignment_role=AssignmentRole.DOORMAN,
            is_active=True,
        )
        .select_related("functionary", "npc_asset")
        .first()
    )
    if doorman is None:
        return

    doorman_name = doorman.get_active_target_name()
    arriving_name = character.key
    room.msg_contents(
        f"{doorman_name} announces: '{arriving_name} has arrived.'",
        exclude=character,
    )
