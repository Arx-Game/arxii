"""Tests for guard detection hook in at_post_move (#2178)."""

from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory


class GuardDetectionHookTests(TestCase):
    def test_at_post_move_calls_check_guard_detection(self):
        """at_post_move should call check_guard_detection via run_safely."""
        room_profile = RoomProfileFactory()
        room = room_profile.objectdb
        char = CharacterFactory(db_key="traveler")
        CharacterSheetFactory(character=char)
        char.location = room
        char.save()

        with patch("world.npc_services.guard_services.check_guard_detection") as mock_check:
            char.at_post_move(source_location=None)
            mock_check.assert_called_once_with(char, char.location)

    def test_at_post_move_guard_detection_failure_does_not_break_move(self):
        """If check_guard_detection raises, at_post_move still completes."""
        room_profile = RoomProfileFactory()
        room = room_profile.objectdb
        char = CharacterFactory(db_key="resilient-traveler")
        CharacterSheetFactory(character=char)
        char.location = room
        char.save()

        with patch(
            "world.npc_services.guard_services.check_guard_detection",
            side_effect=RuntimeError("oops"),
        ):
            # Should not raise — run_safely catches the error.
            char.at_post_move(source_location=None)
