"""GM story-area / story-room services (#2450, epic #2436 slice 3).

Cap enforcement, ownership bookkeeping, and the consent-first join/leave
moves. Check-then-create cap checks follow the codebase norm (no
select_for_update; a double-submit race briefly exceeding a cap is accepted).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.areas.constants import AreaLevel, GridOrigin
from world.gm.models import GMLevelCap, StoryArea, StoryRoomGrant

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from evennia_extensions.models import RoomProfile
    from world.areas.models import Area
    from world.character_sheets.models import CharacterSheet
    from world.gm.models import GMProfile
    from world.instances.models import InstancedRoom


class StoryServiceError(Exception):
    """Refusal with a player-facing message (mirrors GridServiceError)."""

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


def _cap_for(gm: GMProfile) -> GMLevelCap:
    cap = GMLevelCap.objects.filter(level=gm.level).first()
    if cap is None:
        msg = "No GM level caps are configured — ask staff to seed them."
        raise StoryServiceError(msg)
    return cap


def create_story_area(
    *, gm: GMProfile, name: str, description: str = "", skip_cap: bool = False
) -> StoryArea:
    """Create a flat STORY-origin area owned by ``gm``, enforcing max_story_areas.

    ``skip_cap`` mirrors ``story_room_cap_check``'s staff bypass (see
    ``StoryDigRoomAction``) — the staff canvas is uncapped everywhere else in
    this slice, so a staff member holding a GMProfile must not be refused at
    the area cap. A plain GM is always cap-checked; only pass ``skip_cap=True``
    from a caller that has already verified staff standing.
    """
    from world.areas.models import Area  # noqa: PLC0415

    if not skip_cap:
        cap = _cap_for(gm)
        live = StoryArea.objects.filter(gm=gm, area__origin=GridOrigin.STORY).count()
        if live >= cap.max_story_areas:
            msg = (
                f"You already have {live} story area(s) — your level allows "
                f"{cap.max_story_areas}. Remove one first, or ask staff."
            )
            raise StoryServiceError(msg)
    area = Area(
        name=name.strip(),
        level=AreaLevel.BUILDING,
        origin=GridOrigin.STORY,
        description=description,
    )
    area.save()
    return StoryArea.objects.create(gm=gm, area=area)


def remove_story_area(*, story: StoryArea) -> None:
    """Delete an empty story area and its ownership row."""
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415

    if RoomProfile.objects.filter(area=story.area).exists():
        msg = "Remove the area's rooms first."
        raise StoryServiceError(msg)
    area = story.area
    story.delete()
    area.delete()


def story_room_cap_check(*, gm: GMProfile, area: Area) -> None:
    """Raise when digging one more room would exceed max_story_rooms_per_area."""
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415

    cap = _cap_for(gm)
    count = RoomProfile.objects.filter(area=area).count()
    if count >= cap.max_story_rooms_per_area:
        msg = (
            f"This story area already has {count} room(s) — your level allows "
            f"{cap.max_story_rooms_per_area} per area."
        )
        raise StoryServiceError(msg)


def grant_story_room(
    *, gm: GMProfile, room_profile: RoomProfile, sheet: CharacterSheet
) -> StoryRoomGrant:
    """Grant ``sheet`` access to join ``room_profile`` (idempotent)."""
    grant, _created = StoryRoomGrant.objects.get_or_create(
        room=room_profile,
        character=sheet,
        defaults={"granted_by": gm},
    )
    return grant


def revoke_story_room(*, grant: StoryRoomGrant) -> None:
    """Delete the grant; if the character is inside, return them first.

    ``_return_character`` only completes normally when the move succeeds, so a
    stuck character (blocked ``move_to``) keeps the grant instead of losing it.
    """
    char = grant.character.character
    if char is not None and char.location == grant.room.objectdb:
        _return_character(grant)
    grant.delete()


def join_story_room(*, sheet: CharacterSheet, room_profile: RoomProfile) -> ObjectDB:
    """Move the character in (their own action), capturing where they came from."""
    grant = StoryRoomGrant.objects.filter(room=room_profile, character=sheet).first()
    if grant is None:
        msg = "You have no invitation to that room."
        raise StoryServiceError(msg)
    char = sheet.character
    origin = char.location
    moved = char.move_to(room_profile.objectdb, quiet=True)
    if not moved:
        msg = "Something blocked the move — you haven't joined. Try again or ask your GM."
        raise StoryServiceError(msg)
    grant.return_location = origin
    grant.save(update_fields=["return_location"])
    return room_profile.objectdb


def leave_story_room(*, sheet: CharacterSheet, room_profile: RoomProfile) -> ObjectDB:
    """Move the character back to where they joined from (fallback: home)."""
    grant = StoryRoomGrant.objects.filter(room=room_profile, character=sheet).first()
    if grant is None:
        msg = "You have no invitation to that room."
        raise StoryServiceError(msg)
    return _return_character(grant)


def _return_character(grant: StoryRoomGrant) -> ObjectDB:
    char = grant.character.character
    destination = grant.return_location or char.home
    if destination is None:
        msg = "Nowhere to return you to — ask staff."
        raise StoryServiceError(msg)
    moved = char.move_to(destination, quiet=True)
    if not moved:
        msg = "Something blocked the return move — ask staff."
        raise StoryServiceError(msg)
    grant.return_location = None
    grant.save(update_fields=["return_location"])
    return destination


def spin_up_scene_room(*, gm: GMProfile, name: str, description: str) -> InstancedRoom:
    """Spawn a GM-owned temp scene room on the existing instances lifecycle."""
    from world.instances.services import spawn_instanced_room  # noqa: PLC0415

    room = spawn_instanced_room(
        name=name,
        description=description,
        owner=None,
        return_location=None,
        source_key=f"gm:{gm.pk}",
        gm_owner=gm,
    )
    return room.instance_data


def close_scene_room(*, instance: InstancedRoom) -> None:
    """Return every joined character per their grant, then complete the instance.

    Deliberately no ``transaction.atomic()`` here: ``move_to`` triggers room
    hooks with non-DB side effects (messaging, scene bookkeeping) that a DB
    rollback cannot undo, so wrapping this in a transaction would only roll
    back the grant/instance rows while leaving those side effects applied —
    an inconsistent half-state disguised as atomic. Instead this stays
    retryable: if any present character fails to return (blocked ``move_to``),
    no grant is deleted and the instance is not completed, so the whole close
    can simply be attempted again once whatever blocked the move is cleared.
    """
    from world.instances.services import complete_instanced_room  # noqa: PLC0415

    grants = StoryRoomGrant.objects.filter(room__objectdb=instance.room).select_related(
        "character", "room"
    )
    failures: list[str] = []
    for grant in grants:
        char = grant.character.character
        if char is None or char.location != instance.room:
            continue
        try:
            _return_character(grant)
        except StoryServiceError:
            failures.append(str(char))

    if failures:
        names = ", ".join(failures)
        msg = f"Could not return: {names}. Try closing again once they're clear."
        raise StoryServiceError(msg)

    grants.delete()
    complete_instanced_room(instance.room)
