"""Dream realm service functions (#2290, #3003)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.dreams.models import DreamwalkPresence


def get_dream_space(*, room: ObjectDB) -> ObjectDB | None:  # noqa: OBJECTDB_PARAM
    """Return the dream room for a physical waking room.

    Returns the DreamReflection's dream_room if one exists and is active;
    falls back to the liminal dream room (#2287) if not.

    Returns an **ObjectDB** deliberately, even though `DreamReflection.dream_room`
    is a RoomProfile since #2608: three of the four callers (`look` perception,
    `Character.msg_room_state`, the dreamwalk action) want a room object to
    perceive or move into, and only `is_dream_engaged` wants a profile — and it
    gets there with a pk lookup, since RoomProfile shares ObjectDB's pk. Handing
    back the profile would push a `.objectdb` hop onto the majority.

    Args:
        room: An ObjectDB room instance (the physical waking room) — the
            caller almost always holds ``character.location``.

    Returns:
        The ObjectDB dream room to perceive, or None on an unseeded database.
    """
    from world.dreams.models import DreamReflection  # noqa: PLC0415

    reflection = DreamReflection.objects.for_waking_room(room)
    if reflection is not None:
        return reflection.dream_room.objectdb
    from world.vitals.services import get_dream_room  # noqa: PLC0415

    return get_dream_room()


def _character_location(sheet: CharacterSheet | None) -> ObjectDB | None:
    """The sheet's puppet location, or None when unbound/roomless."""
    if sheet is None:
        return None
    character = sheet.character
    if character is None:
        return None
    return character.location


def dreamspace_for(sheet: CharacterSheet | None) -> ObjectDB | None:
    """The dreamspace this sheet perceives, honouring an active dreamwalk.

    The single resolution point for "whose dreamspace is this character in".
    Every viewer-facing caller (look, the web room-state push, the
    dream-engagement wake gate) must route through here so telnet and web
    never disagree.
    """
    from world.dreams.models import DreamwalkPresence  # noqa: PLC0415
    from world.vitals.services import perceives_dreamside  # noqa: PLC0415

    if sheet is None:
        return None
    presence = DreamwalkPresence.objects.filter(dreamer=sheet).select_related("host").first()
    if presence is not None and perceives_dreamside(presence.host):
        host_location = _character_location(presence.host)
        if host_location is not None:
            return get_dream_space(room=host_location)
    own_location = _character_location(sheet)
    if own_location is None:
        return None
    return get_dream_space(room=own_location)


def co_dreamers_for(sheet: CharacterSheet) -> list[CharacterSheet]:
    """Other dreamside sheets resolving to the same dreamspace as ``sheet``.

    Resolves the anchor sheet (the host being dreamwalked to, or ``sheet``
    itself when not walking), then a single query for every sheet anchored
    on it (the anchor plus anyone dreamwalking to the anchor) — no queries
    in a loop.
    """
    from django.db.models import Q  # noqa: PLC0415

    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
    from world.dreams.models import DreamwalkPresence  # noqa: PLC0415
    from world.vitals.services import perceives_dreamside  # noqa: PLC0415

    target = dreamspace_for(sheet)
    if target is None:
        return []
    presence = DreamwalkPresence.objects.filter(dreamer=sheet).select_related("host").first()
    anchor = presence.host if presence is not None else sheet
    candidates = CharacterSheet.objects.filter(
        Q(pk=anchor.pk) | Q(dreamwalk_presence__host=anchor)
    ).exclude(pk=sheet.pk)
    return [candidate for candidate in candidates if perceives_dreamside(candidate)]


def start_dreamwalk(*, dreamer: CharacterSheet, host: CharacterSheet) -> DreamwalkPresence:
    """Anchor ``dreamer``'s perception to ``host``'s dreamspace (idempotent)."""
    from world.dreams.models import DreamwalkPresence  # noqa: PLC0415

    presence, _ = DreamwalkPresence.objects.update_or_create(
        dreamer=dreamer, defaults={"host": host}
    )
    return presence


def end_dreamwalk(sheet: CharacterSheet) -> ObjectDB | None:
    """Clear any dreamwalk and return the host's location (the wake escape lever)."""
    from world.dreams.models import DreamwalkPresence  # noqa: PLC0415

    presence = DreamwalkPresence.objects.filter(dreamer=sheet).select_related("host").first()
    if presence is None:
        return None
    destination = _character_location(presence.host)
    presence.delete()
    return destination


def has_dream_bond(source_sheet: CharacterSheet, target_sheet: CharacterSheet) -> bool:
    """Check if the source has a thread or soul tether bond to the target."""
    from world.magic.constants import TargetKind  # noqa: PLC0415
    from world.magic.models import Thread  # noqa: PLC0415
    from world.relationships.models import CharacterRelationship  # noqa: PLC0415

    # Check for RELATIONSHIP_TRACK or RELATIONSHIP_CAPSTONE threads
    relationship_kinds = {TargetKind.RELATIONSHIP_TRACK, TargetKind.RELATIONSHIP_CAPSTONE}
    threads = Thread.objects.filter(
        owner=source_sheet,
        target_kind__in=relationship_kinds,
        retired_at__isnull=True,
    )
    for thread in threads:
        if thread.target_kind == TargetKind.RELATIONSHIP_TRACK:
            progress = thread.target_relationship_track
            if progress is not None and progress.relationship.target == target_sheet:
                return True
        elif thread.target_kind == TargetKind.RELATIONSHIP_CAPSTONE:
            capstone = thread.target_capstone
            if capstone is not None and capstone.relationship.target == target_sheet:
                return True

    # Check for soul tether bond
    return CharacterRelationship.objects.filter(
        source=source_sheet,
        target=target_sheet,
        is_soul_tether=True,
    ).exists()
