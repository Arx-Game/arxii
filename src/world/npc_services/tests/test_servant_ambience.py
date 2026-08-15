"""Tests for servant pampering ambience: meal + bath prep (#2989).

Mocks ``is_owner``/``is_tenant`` since the real AreaClosure walk is
Postgres-only (mirrors ``test_servant_fetch.py``'s idiom). The delay is
called with ``evennia.utils.delay`` mocked to fire the completion callback
synchronously so tests don't need a real reactor tick.
"""

from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory, RoomProfileFactory
from world.areas.factories import AreaFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.npc_services.factories import FunctionaryFactory
from world.npc_services.models import AssignmentRole, NPCAssignment, NPCSourceType
from world.npc_services.servant_ambience import (
    BATH_FATIGUE_RECOVERY,
    can_servant_pamper,
    prepare_bath,
    prepare_meal,
)
from world.scenes.factories import PersonaFactory


def _immediate_delay(_seconds, callback, *args, **kwargs):
    """Test double for ``evennia.utils.delay`` — fires the callback synchronously."""
    callback(*args, **kwargs)


class CanServantPamperTests(TestCase):
    def setUp(self) -> None:
        self.area = AreaFactory()
        self.room_profile = RoomProfileFactory(area=self.area)
        self.room = self.room_profile.objectdb
        self.owner_persona = PersonaFactory()
        self.char = CharacterFactory(db_key="resident")
        CharacterSheetFactory(character=self.char)
        self.char.location = self.room
        self.char.save()
        func = FunctionaryFactory(room=self.room_profile)
        self.servant = NPCAssignment.objects.create(
            source_type=NPCSourceType.FUNCTIONARY,
            functionary=func,
            room=self.room_profile,
            assignment_role=AssignmentRole.SERVANT,
            assigned_by=self.owner_persona,
        )

    def test_eligible_when_owner_with_servant(self):
        with (
            patch("world.locations.services.is_owner", return_value=True),
            patch("world.locations.services.is_tenant", return_value=False),
            patch(
                "world.npc_services.servant_ambience.find_servant",
                return_value=self.servant,
            ),
            patch(
                "world.scenes.services.active_persona_for_sheet",
                return_value=self.owner_persona,
            ),
        ):
            self.assertTrue(can_servant_pamper(actor=self.char))

    def test_no_servant_returns_false(self):
        with (
            patch("world.locations.services.is_owner", return_value=True),
            patch("world.locations.services.is_tenant", return_value=False),
            patch(
                "world.npc_services.servant_ambience.find_servant",
                return_value=None,
            ),
            patch(
                "world.scenes.services.active_persona_for_sheet",
                return_value=self.owner_persona,
            ),
        ):
            self.assertFalse(can_servant_pamper(actor=self.char))

    def test_no_standing_returns_false(self):
        with (
            patch("world.locations.services.is_owner", return_value=False),
            patch("world.locations.services.is_tenant", return_value=False),
            patch(
                "world.scenes.services.active_persona_for_sheet",
                return_value=self.owner_persona,
            ),
        ):
            self.assertFalse(can_servant_pamper(actor=self.char))

    def test_no_persona_returns_false(self):
        with patch(
            "world.scenes.services.active_persona_for_sheet",
            return_value=None,
        ):
            self.assertFalse(can_servant_pamper(actor=self.char))


class PrepareMealBathTests(TestCase):
    def setUp(self) -> None:
        self.area = AreaFactory()
        self.room_profile = RoomProfileFactory(area=self.area)
        self.room = self.room_profile.objectdb
        self.owner_persona = PersonaFactory()
        self.char = CharacterFactory(db_key="resident", location=self.room)
        self.sheet = CharacterSheetFactory(character=self.char)
        func = FunctionaryFactory(room=self.room_profile)
        self.servant = NPCAssignment.objects.create(
            source_type=NPCSourceType.FUNCTIONARY,
            functionary=func,
            room=self.room_profile,
            assignment_role=AssignmentRole.SERVANT,
            assigned_by=self.owner_persona,
        )

    def test_prepare_meal_delivers_departure_and_arrival_echo(self):
        with (
            patch("world.npc_services.servant_ambience.delay", side_effect=_immediate_delay),
            patch(
                "world.npc_services.servant_ambience.find_servant",
                return_value=self.servant,
            ),
            patch.object(self.room, "msg_contents") as mock_echo,
        ):
            result = prepare_meal(self.char)
            self.assertTrue(result)
            self.assertEqual(mock_echo.call_count, 2)

    def test_prepare_bath_recovers_fatigue(self):
        from actions.constants import ActionCategory
        from world.fatigue.services import apply_fatigue, get_or_create_fatigue_pool

        apply_fatigue(self.sheet, ActionCategory.PHYSICAL, 50, "medium")
        pool = get_or_create_fatigue_pool(self.sheet)
        before = pool.get_current(ActionCategory.PHYSICAL)

        with (
            patch("world.npc_services.servant_ambience.delay", side_effect=_immediate_delay),
            patch(
                "world.npc_services.servant_ambience.find_servant",
                return_value=self.servant,
            ),
            patch.object(self.room, "msg_contents"),
        ):
            prepare_bath(self.char)

        pool.refresh_from_db()
        after = pool.get_current(ActionCategory.PHYSICAL)
        self.assertLess(after, before)

    def test_ambience_no_ops_when_actor_left_room(self):
        other_room = ObjectDBFactory(db_key="elsewhere", db_typeclass_path="typeclasses.rooms.Room")

        def _move_then_call(_seconds, callback, actor, origin_room, *rest):
            actor.location = other_room
            actor.save()
            callback(actor, origin_room, *rest)

        with (
            patch("world.npc_services.servant_ambience.delay", side_effect=_move_then_call),
            patch(
                "world.npc_services.servant_ambience.find_servant",
                return_value=self.servant,
            ),
            patch.object(self.room, "msg_contents") as mock_echo,
        ):
            prepare_meal(self.char)
            # Only the departure echo fires; the arrival echo no-ops.
            self.assertEqual(mock_echo.call_count, 1)

    def test_bath_fatigue_recovery_magnitude_is_positive(self):
        self.assertGreater(BATH_FATIGUE_RECOVERY, 0)
