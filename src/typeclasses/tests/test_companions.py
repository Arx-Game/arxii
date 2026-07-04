"""Tests for CompanionObject typeclass (#672)."""

from __future__ import annotations

from evennia.utils.test_resources import EvenniaTestCase

from typeclasses.companions import CompanionObject


class CompanionObjectTests(EvenniaTestCase):
    def test_is_not_mechanically_immune(self) -> None:
        from evennia_extensions.factories import CompanionObjectFactory

        companion = CompanionObjectFactory()

        self.assertIsInstance(companion, CompanionObject)
        self.assertFalse(companion.is_mechanically_immune)

    def test_at_post_move_does_not_crash_without_sheet(self) -> None:
        from evennia import create_object

        from evennia_extensions.factories import CompanionObjectFactory

        companion = CompanionObjectFactory()
        room_a = create_object("typeclasses.rooms.Room", key="Room A")
        room_b = create_object("typeclasses.rooms.Room", key="Room B")
        companion.location = room_a

        companion.move_to(room_b, quiet=True)

        self.assertEqual(companion.location, room_b)


class CompanionFollowTests(EvenniaTestCase):
    def test_companion_follows_owner_between_rooms(self) -> None:
        from evennia import create_object

        from evennia_extensions.factories import CompanionObjectFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.companions.factories import CompanionFactory

        room_a = create_object("typeclasses.rooms.Room", key="Room A")
        room_b = create_object("typeclasses.rooms.Room", key="Room B")
        sheet = CharacterSheetFactory()
        owner = sheet.character
        owner.location = room_a
        owner.save()
        companion_obj = CompanionObjectFactory(location=room_a)
        CompanionFactory(owner=sheet, objectdb=companion_obj)
        owner.__dict__.pop("companions", None)  # clear cached_property so it re-queries

        owner.move_to(room_b, quiet=True)

        companion_obj.refresh_from_db()
        self.assertEqual(companion_obj.location, room_b)
