"""Expulsion service (#2989) — the unresistable OOC soft gate.

A room owner shows a disruptive character out: moved outside through an
exit, and BARRED from re-entry until the owner lifts it. Per the ratified
#2989 amendments this is a consent/disruption valve, NOT a combat surface —
no check, no roll, no prerequisite bypass, regardless of the target's
character power. Authorization is owner-only
(``IsRoomOwnerPrerequisite`` on ``ExpelCharacterAction``); a posted
SERVANT/DOORMAN NPC is narration only (``_escort_name`` below names them as
the one doing the physical escorting when one is on duty) — it is not a
distinct authorization path. Guards and doormen matter most against future
NPC antagonism; this ships the assignment surfaces and the expulsion valve
now, without pre-building anything speculative for that future combat
surface.

Entry enforcement (the re-entry bar) is pre-traversal, so a barred character
never lands in the room at all — checked at every commit-a-move seam:
``flows.service_functions.movement.check_exit_traversal`` (ordinary exits +
``TravelAction``'s walking hop pacing), ``world.magic.services.portal_travel
.perform_portal_travel`` (the portal fast-path ``TravelAction`` tries
first), and ``actions.definitions.movement.HomeAction`` (the ``home``
command, in case a barred character's declared home is the room they were
shown out of).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.npc_services.models import AssignmentRole, ExpulsionBar, NPCAssignment

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.scenes.models import Persona


def _escort_name(room: ObjectDB, *, fallback: str) -> str:
    """The active SERVANT's display name in ``room``, else ``fallback``.

    Narrates the escort as the household's servant when one is posted
    (pampering-precedent naming, mirrors ``guard_services``/``doorman_services``),
    else falls back to the owner acting directly.
    """
    from world.areas.services import get_room_profile  # noqa: PLC0415

    profile = get_room_profile(room)
    if profile is None:
        return fallback
    servant = (
        NPCAssignment.objects.filter(
            room=profile,
            assignment_role=AssignmentRole.SERVANT,
            is_active=True,
        )
        .select_related("functionary", "npc_asset")
        .first()
    )
    return servant.get_active_target_name() if servant else fallback


@transaction.atomic
def expel_character(*, actor: ObjectDB, target: ObjectDB, imposed_by: Persona) -> tuple[bool, str]:
    """Show ``target`` out of ``actor``'s room and bar their re-entry.

    Unresistable: no check, no roll. Picks the room's exits deterministically
    (ordered by ``db_key``) and moves the target through the first one.
    Creates or reactivates an ``ExpulsionBar`` for (room, target's sheet).

    Returns ``(success, message)``.
    """
    from world.areas.services import get_room_profile  # noqa: PLC0415

    room = actor.location
    profile = get_room_profile(room)
    if profile is None:
        return False, "This room has no profile."

    barred_sheet = target.character_sheet
    if barred_sheet is None:
        return False, "That's not someone who can be barred."

    exits = sorted(room.exits, key=lambda exit_obj: exit_obj.db_key)
    if not exits:
        return False, "There's no way to show them out."
    destination = exits[0].destination
    if destination is None:
        return False, "There's no way to show them out."

    escort_name = _escort_name(room, fallback=actor.key)
    target_name = target.key

    room.msg_contents(
        f"{escort_name} escorts {target_name} out, firmly and without a word of argument.",
        exclude=target,
    )
    target.msg(f"{escort_name} shows you out of {room.key}, no argument brooked.")

    target.move_to(destination, quiet=True, move_type="expel")

    ExpulsionBar.objects.update_or_create(
        room=profile,
        barred_sheet=barred_sheet,
        lifted_at=None,
        defaults={"imposed_by": imposed_by, "imposed_at": timezone.now()},
    )

    return True, f"{target_name} has been shown out and barred from returning."


def lift_expulsion_bar(*, room: ObjectDB, name: str) -> tuple[bool, str]:
    """Lift the active ``ExpulsionBar`` in ``room`` matching a character named ``name``.

    Matches case-insensitively against the barred sheet's character key.
    Returns ``(success, message)``.
    """
    from world.areas.services import get_room_profile  # noqa: PLC0415

    profile = get_room_profile(room)
    if profile is None:
        return False, "This room has no profile."

    active_bars = ExpulsionBar.objects.filter(room=profile, lifted_at__isnull=True).select_related(
        "barred_sheet"
    )

    for bar in active_bars:
        character = bar.barred_sheet.character
        if character is not None and character.key.lower() == name.lower():
            bar.lifted_at = timezone.now()
            bar.save(update_fields=["lifted_at"])
            return True, f"The bar on {character.key} has been lifted."

    return False, f"No active bar on '{name}' here."


def active_bar_for(room: ObjectDB, sheet) -> ExpulsionBar | None:
    """Return the active ``ExpulsionBar`` for ``sheet`` in ``room``, or None.

    The single-query read used by ``check_exit_traversal`` pre-traversal.
    """
    from world.areas.services import get_room_profile  # noqa: PLC0415

    profile = get_room_profile(room)
    if profile is None:
        return None
    return ExpulsionBar.objects.filter(
        room=profile, barred_sheet=sheet, lifted_at__isnull=True
    ).first()
