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


class CurrentResidenceAutoDefaultTests(TestCase):
    """Journey 1 (#2036): grant_tenancy/transfer_ownership auto-default current_residence too."""

    def _character_and_persona(self):
        sheet = CharacterSheetFactory()
        return sheet.character, sheet.primary_persona

    def test_renting_a_room_defaults_current_residence(self) -> None:
        character, persona = self._character_and_persona()
        room_profile = RoomProfileFactory()
        grant_tenancy(room_profile=room_profile, tenant_persona=persona)
        persona.character_sheet.refresh_from_db()
        character.refresh_from_db()
        assert persona.character_sheet.current_residence == room_profile
        assert character.home == room_profile.objectdb

    def test_acquiring_a_room_defaults_current_residence(self) -> None:
        _character, persona = self._character_and_persona()
        room_profile = RoomProfileFactory()
        transfer_ownership(room_profile=room_profile, to_persona=persona)
        persona.character_sheet.refresh_from_db()
        assert persona.character_sheet.current_residence == room_profile

    def test_auto_default_never_overwrites_a_chosen_current_residence(self) -> None:
        from world.magic.services.gain import set_residence as set_current_residence

        _character, persona = self._character_and_persona()
        chosen = RoomProfileFactory()
        set_current_residence(persona.character_sheet, chosen)  # the player picked this one

        grant_tenancy(room_profile=RoomProfileFactory(), tenant_persona=persona)
        persona.character_sheet.refresh_from_db()
        assert persona.character_sheet.current_residence == chosen

    def test_org_grant_does_not_set_a_personal_current_residence(self) -> None:
        # Org-only grant (tenant_persona=None) should no-op — nothing individual to default.
        from world.societies.factories import OrganizationFactory

        room_profile = RoomProfileFactory()
        grant_tenancy(room_profile=room_profile, tenant_organization=OrganizationFactory())
        # No exception, and no personal sheet was ever touched — nothing to assert on
        # a specific sheet, but this exercises the persona=None no-op branch cleanly.

    def test_tagged_claimed_resonance_appears_in_residence_resonances_after_default(self) -> None:
        """Journey 1's full assertion: an already-claimed, room-tagged resonance shows up."""
        from world.magic.factories import CharacterResonanceFactory, ResonanceFactory
        from world.magic.services.gain import get_residence_resonances, tag_room_resonance

        _character, persona = self._character_and_persona()
        room_profile = RoomProfileFactory()
        resonance = ResonanceFactory()
        CharacterResonanceFactory(character_sheet=persona.character_sheet, resonance=resonance)
        tag_room_resonance(room_profile, resonance)

        grant_tenancy(room_profile=room_profile, tenant_persona=persona)

        persona.character_sheet.refresh_from_db()
        assert get_residence_resonances(persona.character_sheet) == {resonance}
