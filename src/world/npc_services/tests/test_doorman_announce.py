"""Tests for the doorman announcement service (#2989)."""

from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory, RoomProfileFactory
from world.npc_services.doorman_services import announce_arrival
from world.npc_services.factories import FunctionaryFactory
from world.npc_services.models import AssignmentRole, NPCAssignment, NPCSourceType
from world.scenes.factories import PersonaFactory


class AnnounceArrivalTests(TestCase):
    def setUp(self) -> None:
        self.room_profile = RoomProfileFactory()
        self.room = self.room_profile.objectdb

    def _create_doorman(self):
        func = FunctionaryFactory(room=self.room_profile)
        persona = PersonaFactory()
        return NPCAssignment.objects.create(
            source_type=NPCSourceType.FUNCTIONARY,
            functionary=func,
            room=self.room_profile,
            assignment_role=AssignmentRole.DOORMAN,
            assigned_by=persona,
        )

    def test_no_doorman_short_circuits(self):
        char = CharacterFactory(db_key="arrival", location=self.room)
        with patch.object(self.room, "msg_contents") as mock_echo:
            announce_arrival(char, self.room)
            mock_echo.assert_not_called()

    def test_no_profile_short_circuits(self):
        char = CharacterFactory(db_key="wanderer")
        bare_room = ObjectDBFactory(db_key="bare-room")
        # Should not raise even though the bare room has no profile.
        announce_arrival(char, bare_room)

    def test_announcement_fires_and_excludes_arriving_character(self):
        doorman = self._create_doorman()
        char = CharacterFactory(db_key="Visitor", location=self.room)

        with patch.object(self.room, "msg_contents") as mock_echo:
            announce_arrival(char, self.room)
            mock_echo.assert_called_once()
            args, kwargs = mock_echo.call_args
            self.assertIn(doorman.get_active_target_name(), args[0])
            self.assertIn("Visitor", args[0])
            self.assertEqual(kwargs.get("exclude"), char)
