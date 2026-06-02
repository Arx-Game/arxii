"""Tests for scar-gated MOVED triggers — Issue #526."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, RoomProfileFactory
from flows.constants import EventName


class MovedEventEmissionTest(TestCase):
    """at_post_move emits EventName.MOVED so installed triggers fire."""

    def setUp(self):
        self.room = RoomProfileFactory().objectdb
        self.character = CharacterFactory()
        self.character.db_location = self.room
        self.character.save(update_fields=["db_location"])

    def test_at_post_move_emits_moved_event(self):
        """at_post_move calls emit_event with EventName.MOVED."""
        with patch("typeclasses.characters.emit_event") as mock_emit:
            mock_emit.return_value = MagicMock()
            self.character.at_post_move(source_location=None)

        calls = [c for c in mock_emit.call_args_list if c.args and c.args[0] == EventName.MOVED]
        self.assertTrue(
            len(calls) >= 1,
            "Expected emit_event(EventName.MOVED, ...) to be called from at_post_move",
        )
