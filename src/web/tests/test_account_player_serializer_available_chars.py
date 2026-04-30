"""Tests for AvailableCharacterSerializer used in the account payload."""

from django.test import TestCase
from evennia.utils.create import create_object

from evennia_extensions.factories import (
    AccountFactory,
    CharacterFactory,
    GMCharacterFactory,
    StaffCharacterFactory,
)
from web.api.serializers import AvailableCharacterSerializer
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import (
    RosterEntryFactory,
    RosterFactory,
    RosterTenureFactory,
)
from world.roster.models import RosterType
from world.scenes.constants import PersonaType
from world.scenes.models import Persona


class AvailableCharacterSerializerTests(TestCase):
    """RosterEntry -> AvailableCharacter payload entry."""

    def setUp(self) -> None:
        self.account = AccountFactory()
        self.active_roster = RosterFactory(name=RosterType.ACTIVE)

    def _make_entry(self, character_factory=CharacterFactory):
        """Build an account -> tenure -> entry -> sheet -> character chain."""
        character = character_factory()
        sheet = CharacterSheetFactory(character=character)
        entry = RosterEntryFactory(character_sheet=sheet, roster=self.active_roster)
        RosterTenureFactory(
            player_data=self.account.player_data,
            roster_entry=entry,
        )
        return entry, sheet, character

    def test_basic_pc_payload(self) -> None:
        entry, _sheet, character = self._make_entry()
        data = AvailableCharacterSerializer(entry, context={"puppeted_character_ids": set()}).data
        assert data["id"] == character.id
        assert data["name"] == character.key
        assert data["character_type"] == "PC"
        assert data["roster_status"] == RosterType.ACTIVE
        assert data["currently_puppeted_in_session"] is False

    def test_gm_character_payload(self) -> None:
        entry, _sheet, _char = self._make_entry(character_factory=GMCharacterFactory)
        data = AvailableCharacterSerializer(entry, context={"puppeted_character_ids": set()}).data
        assert data["character_type"] == "GM"

    def test_staff_character_payload(self) -> None:
        entry, _sheet, _char = self._make_entry(character_factory=StaffCharacterFactory)
        data = AvailableCharacterSerializer(entry, context={"puppeted_character_ids": set()}).data
        assert data["character_type"] == "STAFF"

    def test_personas_excludes_temporary(self) -> None:
        entry, sheet, _char = self._make_entry()
        # Sheet already has PRIMARY (auto-created via factory)
        Persona.objects.create(
            character_sheet=sheet,
            name="Hooded Stranger",
            persona_type=PersonaType.ESTABLISHED,
        )
        Persona.objects.create(
            character_sheet=sheet,
            name="Disguise",
            persona_type=PersonaType.TEMPORARY,
        )
        data = AvailableCharacterSerializer(entry, context={"puppeted_character_ids": set()}).data
        persona_types = [p["persona_type"] for p in data["personas"]]
        assert "temporary" not in persona_types
        assert persona_types[0] == "primary"
        assert "established" in persona_types

    def test_currently_puppeted_flag(self) -> None:
        entry, _sheet, character = self._make_entry()
        data = AvailableCharacterSerializer(
            entry, context={"puppeted_character_ids": {character.id}}
        ).data
        assert data["currently_puppeted_in_session"] is True

    def test_last_location_when_set(self) -> None:
        entry, _sheet, character = self._make_entry()
        room = create_object("typeclasses.rooms.Room", key="Throne Room", nohome=True)
        character.location = room
        character.save()
        data = AvailableCharacterSerializer(entry, context={"puppeted_character_ids": set()}).data
        assert data["last_location"] == {"id": room.id, "name": "Throne Room"}

    def test_last_location_when_unset(self) -> None:
        entry, _sheet, character = self._make_entry()
        character.location = None
        character.save()
        data = AvailableCharacterSerializer(entry, context={"puppeted_character_ids": set()}).data
        assert data["last_location"] is None

    def test_portrait_url_when_unset(self) -> None:
        entry, _sheet, _char = self._make_entry()
        data = AvailableCharacterSerializer(entry, context={"puppeted_character_ids": set()}).data
        assert data["portrait_url"] is None
