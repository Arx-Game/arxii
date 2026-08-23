"""Guard detection service (#2178).

Post-arrival guard detection: when a character enters a room that has an
active GUARD ``NPCAssignment``, and the character lacks owner/tenant standing,
the guard notices them — automatically for a loud (non-sneaking) entrant, or
after winning the SNEAK security-oracle contest against a sneaking one (#3288;
a guard win also strips the sneak stance). On detection, emit a room echo and
alert the owner if online and co-located.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.npc_services.models import AssignmentRole, NPCAssignment

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.scenes.models import Persona

#: PLACEHOLDER difficulty for the guard detection check. A SNEAKING intruder
#: rolls the SNEAK security oracle against this difficulty; a failed check
#: (success_level <= 0) = detected and the stance is stripped. Loud entrants
#: don't roll at all (#3288). #2180 may refine this into an opposed Perception
#: roll or a per-NPC value.
GUARD_DETECTION_DIFFICULTY = 50


def check_guard_detection(character: ObjectDB, room: ObjectDB) -> None:
    """Post-arrival guard detection check.

    Called from ``Character.at_post_move``. If the destination room has an
    active GUARD assignment and the arriving character lacks owner/tenant
    standing, roll guard detection vs. the intruder's Stealth. On failure,
    emit a room echo and alert the owner if online and in the room.

    Short-circuits (no DB queries past the initial check) when the room has
    no active guard assignments.

    Args:
        character: The character who just arrived.
        room: The Evennia room ObjectDB the character arrived in.
    """
    from world.areas.services import get_room_profile  # noqa: PLC0415

    profile = get_room_profile(room)
    if profile is None:
        return

    guard_assignment = (
        NPCAssignment.objects.filter(
            room=profile,
            assignment_role=AssignmentRole.GUARD,
            is_active=True,
        )
        .select_related("functionary", "npc_asset")
        .first()
    )
    if guard_assignment is None:
        return

    # Resolve the arriving character's active persona.
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    try:
        sheet = character.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        return
    persona = active_persona_for_sheet(sheet)
    if persona is None:
        return

    # Authorized entrants don't trigger detection.
    from world.locations.services import is_owner, is_tenant  # noqa: PLC0415

    if is_owner(persona, room) or is_tenant(persona, room):
        return

    # #3288: detection branches on the sneak stance. A loud (non-sneaking)
    # unauthorized entrant is simply noticed — no free roll (the old per-entry
    # "dice tax" is gone). A sneaking entrant contests the SNEAK security
    # oracle against the guard's difficulty; a guard win strips the stance
    # publicly (being spotted means being SEEN).
    from world.checks.constants import SecurityCheckKind  # noqa: PLC0415
    from world.checks.security_services import resolve_security_check  # noqa: PLC0415
    from world.stealth.services import (  # noqa: PLC0415
        is_sneaking,
        refresh_room_state,
        stop_sneaking,
    )

    if is_sneaking(character):
        try:
            result = resolve_security_check(
                SecurityCheckKind.SNEAK,
                character,
                target_difficulty=GUARD_DETECTION_DIFFICULTY,
            )
        except ValueError:
            # Stealth CheckType unseeded — treat as an ordinary loud entry.
            result = None
        if result is not None and result.success_level > 0:
            return
        stop_sneaking(character)
        refresh_room_state(character)

    _emit_guard_alert(character, room, guard_assignment)


def _emit_guard_alert(
    character: ObjectDB,
    room: ObjectDB,
    assignment: NPCAssignment,
) -> None:
    """Emit a room echo and alert the owner on successful guard detection.

    Args:
        character: The detected intruder.
        room: The room where detection occurred.
        assignment: The active guard assignment that detected them.
    """
    from world.locations.services import effective_owner  # noqa: PLC0415

    guard_name = assignment.get_active_target_name()

    # Room echo — visible to all occupants except the intruder gets a
    # different message (they know they've been spotted).
    room.msg_contents(
        f"|y{guard_name} calls out: 'Halt! Who goes there?'|n",
        exclude=character,
    )
    character.msg(f"|y{guard_name} spots you and raises the alarm!|n")

    # Alert the owner if online and in the room.
    ownership = effective_owner(room)
    if ownership is not None:
        owner_target = ownership.get_active_target()
        if owner_target is not None:
            _alert_owner(owner_target, room, character, guard_name)


def _alert_owner(
    owner_target: Persona | object,
    room: ObjectDB,
    intruder: ObjectDB,
    guard_name: str,
) -> None:
    """Send a direct .msg() to the owner if they are online and in the room.

    Args:
        owner_target: The Persona or Organization that owns the room.
        room: The room where detection occurred.
        intruder: The detected intruder.
        guard_name: The guard's display name.
    """
    from world.scenes.models import Persona  # noqa: PLC0415

    if not isinstance(owner_target, Persona):
        # Org owner — alert all online org members in the room.
        from world.societies.models import OrganizationMembership  # noqa: PLC0415

        memberships = OrganizationMembership.objects.filter(
            organization=owner_target,
            left_at__isnull=True,
            exiled_at__isnull=True,
        ).select_related("persona")
        for membership in memberships:
            _msg_persona_if_in_room(membership.persona, room, intruder, guard_name)
        return

    _msg_persona_if_in_room(owner_target, room, intruder, guard_name)


def _msg_persona_if_in_room(
    persona: Persona,
    room: ObjectDB,
    intruder: ObjectDB,
    guard_name: str,
) -> None:
    """Send an alert .msg() to the persona's character if they're in the room.

    Args:
        persona: The owner's persona.
        room: The room where detection occurred.
        intruder: The detected intruder.
        guard_name: The guard's display name.
    """
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415

    sheet = CharacterSheet.objects.filter(primary_persona=persona).first()
    if sheet is None:
        return
    char = sheet.character
    if char is None or char.location != room:
        return
    intruder_name = intruder.key if intruder else "Someone"
    char.msg(f"|r{guard_name} reports: an intruder ({intruder_name}) has entered!|n")
