"""Tests for maybe_emit_fall: emits FELL on CHASM entry, silent otherwise.

Built in setUp rather than setUpTestData: factories create Evennia ObjectDB instances
(DbHolder — not deepcopyable), which would break setUpTestData's deepcopy.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from flows.constants import EventName
from world.areas.positioning.constants import PositionKind
from world.areas.positioning.models import Position
from world.areas.positioning.services import maybe_emit_fall


class MaybeEmitFallTests(TestCase):
    def setUp(self) -> None:
        from evennia import create_object

        from evennia_extensions.factories import CharacterFactory

        self.room = create_object("typeclasses.rooms.Room", key="FallTestRoom", nohome=True)
        self.char = CharacterFactory(location=self.room)

    def test_emits_fell_on_chasm_entry(self) -> None:
        chasm = Position.objects.create(room=self.room, name="the pit", kind=PositionKind.CHASM)
        with patch("flows.emit.emit_event") as mock_emit:
            emitted = maybe_emit_fall(self.char, chasm)
        self.assertTrue(emitted)
        args, _kwargs = mock_emit.call_args
        self.assertEqual(args[0], EventName.FELL)

    def test_no_emit_on_ground(self) -> None:
        ground = Position.objects.create(room=self.room, name="floor", kind=PositionKind.PRIMARY)
        with patch("flows.emit.emit_event") as mock_emit:
            emitted = maybe_emit_fall(self.char, ground)
        self.assertFalse(emitted)
        mock_emit.assert_not_called()
