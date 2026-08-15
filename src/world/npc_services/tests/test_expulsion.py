"""Tests for the expulsion service + ExpulsionBar model (#2989).

The core invariant under test: expulsion CANNOT be resisted — no check, no
roll, no prerequisite bypass — and the bar it writes actually blocks
re-entry (proven at the ``check_exit_traversal`` seam in
``flows/tests/test_movement.py``, not duplicated here).
"""

from django.db import IntegrityError, transaction
from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.npc_services.expulsion_services import (
    active_bar_for,
    expel_character,
    lift_expulsion_bar,
)
from world.npc_services.models import ExpulsionBar
from world.scenes.factories import PersonaFactory


class ExpulsionBarModelTests(TestCase):
    def test_unique_active_bar_per_room_sheet(self):
        """Two active bars for the same (room, sheet) collide."""
        room = RoomProfileFactory()
        char = CharacterFactory(db_key="barred")
        sheet = CharacterSheetFactory(character=char)
        persona = PersonaFactory()

        ExpulsionBar.objects.create(room=room, barred_sheet=sheet, imposed_by=persona)
        with transaction.atomic(), self.assertRaises(IntegrityError):
            ExpulsionBar.objects.create(room=room, barred_sheet=sheet, imposed_by=persona)

    def test_lifted_bar_does_not_collide(self):
        """A lifted bar + a fresh active one for the same (room, sheet) → OK."""
        from django.utils import timezone

        room = RoomProfileFactory()
        char = CharacterFactory(db_key="barred")
        sheet = CharacterSheetFactory(character=char)
        persona = PersonaFactory()

        old = ExpulsionBar.objects.create(room=room, barred_sheet=sheet, imposed_by=persona)
        old.lifted_at = timezone.now()
        old.save()

        ExpulsionBar.objects.create(room=room, barred_sheet=sheet, imposed_by=persona)


class ExpelCharacterServiceTests(TestCase):
    def setUp(self) -> None:
        self.room = ObjectDBFactory(db_key="parlor", db_typeclass_path="typeclasses.rooms.Room")
        self.outside = ObjectDBFactory(db_key="street", db_typeclass_path="typeclasses.rooms.Room")
        ObjectDBFactory(
            db_key="out",
            db_typeclass_path="typeclasses.exits.Exit",
            location=self.room,
            destination=self.outside,
        )
        self.actor = CharacterFactory(db_key="Owner", location=self.room)
        self.target = CharacterFactory(db_key="Disruptor", location=self.room)
        CharacterSheetFactory(character=self.target)
        self.persona = PersonaFactory()

    def test_expel_moves_target_and_bars_reentry(self):
        success, _message = expel_character(
            actor=self.actor, target=self.target, imposed_by=self.persona
        )
        self.assertTrue(success)
        self.target.refresh_from_db()
        self.assertEqual(self.target.location, self.outside)

        from world.areas.services import get_room_profile

        profile = get_room_profile(self.room)
        bar = active_bar_for(self.room, self.target.character_sheet)
        self.assertIsNotNone(bar)
        self.assertEqual(bar.room_id, profile.pk)

    def test_expel_with_no_exit_fails_cleanly(self):
        bare_room = ObjectDBFactory(db_key="sealed", db_typeclass_path="typeclasses.rooms.Room")
        actor = CharacterFactory(db_key="Owner2", location=bare_room)
        target = CharacterFactory(db_key="Disruptor2", location=bare_room)
        CharacterSheetFactory(character=target)

        success, message = expel_character(actor=actor, target=target, imposed_by=self.persona)
        self.assertFalse(success)
        self.assertIn("no way", message.lower())

    def test_lift_expulsion_bar_by_name(self):
        expel_character(actor=self.actor, target=self.target, imposed_by=self.persona)
        self.assertIsNotNone(active_bar_for(self.room, self.target.character_sheet))

        success, _message = lift_expulsion_bar(room=self.room, name="Disruptor")
        self.assertTrue(success)
        self.assertIsNone(active_bar_for(self.room, self.target.character_sheet))

    def test_lift_expulsion_bar_no_match(self):
        success, _message = lift_expulsion_bar(room=self.room, name="Nobody")
        self.assertFalse(success)

    def test_active_bar_for_returns_none_when_no_bar_exists(self):
        clean_room = ObjectDBFactory(
            db_key="clean-room", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.assertIsNone(active_bar_for(clean_room, self.target.character_sheet))
