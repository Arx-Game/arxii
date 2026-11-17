"""What a character perceives of Primum (#5125).

A caster always knows the substance she works herself, and knows another substance in a place
only once she has sensed it there (a ``PrimumSighting``). The read is what the cast card uses
to decide whether it may name a substance that works against her.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from evennia_extensions.models import RoomProfile
from world.character_sheets.models import CharacterSheet
from world.magic.models import CharacterGift, PrimumSighting
from world.magic.services.primum import gift_substance

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


def perceived_substance_ids(character: ObjectDB, room: ObjectDB | None) -> frozenset[int]:
    """The substances ``character`` perceives in ``room``.

    The caster's sightings for that room, plus the substance of each gift she holds (resolved
    through the gift's lineage). A character with no sheet perceives nothing.
    """
    try:
        sheet = character.sheet_data
    except CharacterSheet.DoesNotExist:
        return frozenset()
    perceived: set[int] = set()
    for held in CharacterGift.objects.filter(character=sheet).select_related("gift"):
        substance = gift_substance(held.gift)
        if substance is not None:
            perceived.add(substance.pk)
    if room is not None:
        try:
            profile = room.room_profile
        except RoomProfile.DoesNotExist:
            return frozenset(perceived)
        perceived.update(
            PrimumSighting.objects.filter(character_sheet=sheet, room_profile=profile).values_list(
                "substance_id", flat=True
            )
        )
    return frozenset(perceived)
