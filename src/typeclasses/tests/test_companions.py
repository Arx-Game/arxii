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
