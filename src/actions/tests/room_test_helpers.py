"""Shared room/character fixtures for prerequisite and action tests that need a
character standing in a specific room with an active persona.
"""

from __future__ import annotations

from evennia_extensions.models import RoomProfile
from world.character_sheets.factories import CharacterSheetFactory


def character_in_room(room_profile: RoomProfile):
    """A fresh character (with a CharacterSheet + primary persona) standing in
    ``room_profile``'s room. Returns ``(sheet, character)``.
    """
    sheet = CharacterSheetFactory()
    character = sheet.character
    character.location = room_profile.objectdb
    character.save()
    return sheet, character
