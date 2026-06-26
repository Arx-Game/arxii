"""Primary residence (#1514): set_residence + auto-default on first rent/acquire.

Residence reuses Evennia's ``home`` (what ``CmdHome`` recalls to). Renting or acquiring a room
defaults it as home when the character hasn't chosen one; an existing choice is never clobbered.
"""

from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.locations.services import (
    grant_tenancy,
    set_residence,
    transfer_ownership,
)


class ResidenceTests(TestCase):
    def _character_and_persona(self):
        sheet = CharacterSheetFactory()
        return sheet.character, sheet.primary_persona

    def test_set_residence_sets_home(self) -> None:
        character, _ = self._character_and_persona()
        room = RoomProfileFactory().objectdb
        set_residence(character=character, room=room)
        assert character.home == room

    def test_renting_a_room_defaults_it_as_home(self) -> None:
        character, persona = self._character_and_persona()
        room_profile = RoomProfileFactory()
        grant_tenancy(room_profile=room_profile, tenant_persona=persona)
        assert character.home == room_profile.objectdb

    def test_acquiring_a_room_defaults_it_as_home(self) -> None:
        character, persona = self._character_and_persona()
        room_profile = RoomProfileFactory()
        transfer_ownership(room_profile=room_profile, to_persona=persona)
        assert character.home == room_profile.objectdb

    def test_auto_default_never_overwrites_a_chosen_residence(self) -> None:
        character, persona = self._character_and_persona()
        chosen = RoomProfileFactory().objectdb
        set_residence(character=character, room=chosen)  # the player picked this one

        grant_tenancy(room_profile=RoomProfileFactory(), tenant_persona=persona)
        assert character.home == chosen  # a later rental doesn't move their home

    def test_org_and_area_grants_do_not_set_a_personal_home(self) -> None:
        # Area-level tenancy (no room) has no single room to home to → no-op, no error.
        character, persona = self._character_and_persona()
        from world.areas.constants import AreaLevel
        from world.areas.factories import AreaFactory

        before = character.home
        grant_tenancy(area=AreaFactory(level=AreaLevel.WARD), tenant_persona=persona)
        assert character.home == before
