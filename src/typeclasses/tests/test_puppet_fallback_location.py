"""A character with nowhere to be lands in the fallback starting room (#3818).

Evennia's ``at_pre_puppet`` restores ``prelogout_location`` or ``home`` and, when
both are empty, leaves the character with no location and tells the account so.
The web client then waits forever for a ``room_state`` frame that a location-less
character can never send. Our override gives such a character the canonical
fallback room as ``home`` first — found by its stable fixture identity, so a
staff rename ("City Center") does not break it — and lets Evennia's own restore
move them there.
"""

from __future__ import annotations

from unittest.mock import Mock

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.seeds.character_creation import ensure_canonical_fallback_room

ROOM = "typeclasses.rooms.Room"


class FallbackLocationOnPuppetTests(TestCase):
    def setUp(self) -> None:
        self.account = Mock()
        self.fallback = ensure_canonical_fallback_room()

    def _homeless_character(self):
        character = CharacterFactory(location=None, home=None)
        character.attributes.remove("prelogout_location")
        self.assertIsNone(character.location)
        self.assertIsNone(character.home)
        return character

    def test_lands_in_the_fallback_room_and_keeps_it_as_home(self) -> None:
        character = self._homeless_character()

        character.at_pre_puppet(self.account)

        self.assertEqual(character.location, self.fallback)
        self.assertEqual(character.home, self.fallback)
        self.account.msg.assert_not_called()

    def test_follows_a_staff_rename_of_the_fallback_room(self) -> None:
        """The room is found by fixture identity, not by the seeded name."""
        self.fallback.key = "City Center"
        self.fallback.save()
        character = self._homeless_character()

        character.at_pre_puppet(self.account)

        self.assertEqual(character.location.key, "City Center")

    def test_prelogout_location_still_wins(self) -> None:
        elsewhere = ObjectDBFactory(db_typeclass_path=ROOM)
        character = self._homeless_character()
        character.db.prelogout_location = elsewhere

        character.at_pre_puppet(self.account)

        self.assertEqual(character.location, elsewhere)

    def test_an_existing_home_still_wins(self) -> None:
        home = ObjectDBFactory(db_typeclass_path=ROOM)
        character = CharacterFactory(location=None, home=home)
        character.attributes.remove("prelogout_location")

        character.at_pre_puppet(self.account)

        self.assertEqual(character.location, home)
        self.assertEqual(character.home, home)

    def test_a_character_already_somewhere_is_left_alone(self) -> None:
        here = ObjectDBFactory(db_typeclass_path=ROOM)
        character = CharacterFactory(location=here, home=None)

        character.at_pre_puppet(self.account)

        self.assertEqual(character.location, here)
        self.assertIsNone(character.home)


class NoFallbackSeededTests(TestCase):
    def test_degrades_to_evennias_own_message_without_raising(self) -> None:
        account = Mock()
        character = CharacterFactory(location=None, home=None)
        character.attributes.remove("prelogout_location")

        character.at_pre_puppet(account)

        self.assertIsNone(character.location)
        account.msg.assert_called_once()
