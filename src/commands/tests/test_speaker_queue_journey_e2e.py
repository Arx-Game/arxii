"""E2E journey test for the speaker queue lifecycle (#2356).

Full lifecycle: open → join (two personas) → advance → skip → leave → close.
Exercises the Actions through ``Action().run()`` — the same seam telnet and
web converge on.

DbHolder trap: all Evennia ObjectDB instances live in setUp, not setUpTestData.
"""

from __future__ import annotations

from django.test import TestCase

from actions.definitions.speaker_queue import (
    AdvanceSpeakerQueueAction,
    CloseSpeakerQueueAction,
    JoinSpeakerQueueAction,
    LeaveSpeakerQueueAction,
    OpenSpeakerQueueAction,
    SkipSpeakerAction,
)
from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.speaker_queue_models import SpeakerQueue


def _create_pc(db_key: str, location=None):
    """Create a PC character with a live roster tenure."""
    kwargs = {"db_key": db_key}
    if location is not None:
        kwargs["location"] = location
    char = ObjectDBFactory(db_typeclass_path="typeclasses.characters.Character", **kwargs)
    CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet__character=char)
    tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
    _ = tenure.player_data.account
    return char


class SpeakerQueueJourneyE2E(TestCase):
    """Full lifecycle E2E test for the speaker queue."""

    def setUp(self) -> None:
        self.room = ObjectDBFactory(
            db_key="QueueRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.alice = _create_pc("Alice", location=self.room)
        self.bob = _create_pc("Bob", location=self.room)
        self.carol = _create_pc("Carol", location=self.room)

    def test_full_journey(self):
        """open → join → join → advance → skip → leave → close."""
        # 1. Open the queue
        result = OpenSpeakerQueueAction().run(actor=self.alice)
        self.assertTrue(result.success, result.message)

        # 2. Alice and Bob join
        result = JoinSpeakerQueueAction().run(actor=self.alice)
        self.assertTrue(result.success)
        self.assertIn("position 1", result.message)

        result = JoinSpeakerQueueAction().run(actor=self.bob)
        self.assertTrue(result.success)
        self.assertIn("position 2", result.message)

        # 3. Carol joins
        result = JoinSpeakerQueueAction().run(actor=self.carol)
        self.assertTrue(result.success)
        self.assertIn("position 3", result.message)

        # 4. Alice (current speaker) advances
        result = AdvanceSpeakerQueueAction().run(actor=self.alice)
        self.assertTrue(result.success)
        self.assertIn("Bob", result.message)

        # 5. Skip Carol (position 3 now, since Bob moved to 1 and Carol to 2)
        result = SkipSpeakerAction().run(actor=self.alice, target_name="Carol")
        self.assertTrue(result.success)

        # 6. Bob leaves
        result = LeaveSpeakerQueueAction().run(actor=self.bob)
        self.assertTrue(result.success)

        # 7. Close the queue (Alice opened it)
        result = CloseSpeakerQueueAction().run(actor=self.alice)
        self.assertTrue(result.success)

        queue = SpeakerQueue.objects.get(room=self.room)
        self.assertFalse(queue.is_active)

    def test_advance_by_non_current_non_opener_fails(self):
        """Bob can't advance when Alice is current and Bob isn't the opener."""
        OpenSpeakerQueueAction().run(actor=self.alice)
        JoinSpeakerQueueAction().run(actor=self.alice)
        JoinSpeakerQueueAction().run(actor=self.bob)

        result = AdvanceSpeakerQueueAction().run(actor=self.bob)
        self.assertFalse(result.success)

    def test_open_twice_fails(self):
        """Can't open two queues in the same room."""
        result = OpenSpeakerQueueAction().run(actor=self.alice)
        self.assertTrue(result.success)

        result = OpenSpeakerQueueAction().run(actor=self.bob)
        self.assertFalse(result.success)

    def test_close_by_non_opener_fails(self):
        """Only the opener or staff can close."""
        OpenSpeakerQueueAction().run(actor=self.alice)
        result = CloseSpeakerQueueAction().run(actor=self.bob)
        self.assertFalse(result.success)
