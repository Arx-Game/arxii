"""Tests for speaker queue service functions (#2356)."""

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.factories import PersonaFactory, SceneFactory
from world.scenes.speaker_queue_services import (
    SpeakerQueueError,
    advance_queue,
    clear_queue_on_scene_finish,
    close_queue,
    get_active_queue,
    join_queue,
    leave_queue,
    open_queue,
    queue_entries,
    remove_persona_from_room_queues,
    skip_speaker,
)


class SpeakerQueueServiceTests(TestCase):
    """Tests for the speaker queue service layer."""

    def setUp(self) -> None:
        self.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.sheet_a = CharacterSheetFactory()
        self.persona_a = self.sheet_a.primary_persona
        self.persona_b = PersonaFactory(character_sheet=self.sheet_a, name="Bob")
        self.persona_c = PersonaFactory(character_sheet=self.sheet_a, name="Carol")

    def test_open_queue_creates_active_queue(self):
        queue = open_queue(self.room, self.persona_a)
        self.assertTrue(queue.is_active)
        self.assertEqual(queue.room, self.room)
        self.assertEqual(queue.opened_by, self.persona_a)
        self.assertIsNone(queue.closed_at)

    def test_open_queue_errors_if_already_active(self):
        open_queue(self.room, self.persona_a)
        with self.assertRaises(SpeakerQueueError):
            open_queue(self.room, self.persona_b)

    def test_open_queue_stamps_scene_if_active(self):
        scene = SceneFactory(location=self.room, is_active=True)
        queue = open_queue(self.room, self.persona_a)
        self.assertEqual(queue.scene, scene)

    def test_close_queue_sets_inactive(self):
        queue = open_queue(self.room, self.persona_a)
        close_queue(queue)
        queue.refresh_from_db()
        self.assertFalse(queue.is_active)
        self.assertIsNotNone(queue.closed_at)

    def test_join_queue_appends_at_end(self):
        queue = open_queue(self.room, self.persona_a)
        e1 = join_queue(queue, self.persona_a)
        e2 = join_queue(queue, self.persona_b)
        self.assertEqual(e1.position, 1)
        self.assertEqual(e2.position, 2)

    def test_join_queue_errors_if_already_joined(self):
        queue = open_queue(self.room, self.persona_a)
        join_queue(queue, self.persona_a)
        with self.assertRaises(SpeakerQueueError):
            join_queue(queue, self.persona_a)

    def test_leave_queue_renumbers(self):
        queue = open_queue(self.room, self.persona_a)
        join_queue(queue, self.persona_a)
        join_queue(queue, self.persona_b)
        join_queue(queue, self.persona_c)
        leave_queue(queue, self.persona_b)
        entries = list(queue_entries(queue))
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].persona, self.persona_a)
        self.assertEqual(entries[0].position, 1)
        self.assertEqual(entries[1].persona, self.persona_c)
        self.assertEqual(entries[1].position, 2)

    def test_advance_queue_removes_current_and_returns_next(self):
        queue = open_queue(self.room, self.persona_a)
        join_queue(queue, self.persona_a)
        join_queue(queue, self.persona_b)
        next_entry = advance_queue(queue)
        self.assertIsNotNone(next_entry)
        self.assertEqual(next_entry.persona, self.persona_b)
        self.assertEqual(next_entry.position, 1)
        self.assertEqual(queue_entries(queue).count(), 1)

    def test_advance_queue_returns_none_when_empty(self):
        queue = open_queue(self.room, self.persona_a)
        next_entry = advance_queue(queue)
        self.assertIsNone(next_entry)

    def test_skip_speaker_removes_named_persona(self):
        queue = open_queue(self.room, self.persona_a)
        join_queue(queue, self.persona_a)
        join_queue(queue, self.persona_b)
        join_queue(queue, self.persona_c)
        # Skip Bob (position 2 — not current)
        next_entry = skip_speaker(queue, self.persona_b)
        self.assertIsNone(next_entry)  # Bob wasn't current
        entries = list(queue_entries(queue))
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[1].persona, self.persona_c)
        self.assertEqual(entries[1].position, 2)

    def test_skip_speaker_returns_new_current_if_skipping_current(self):
        queue = open_queue(self.room, self.persona_a)
        join_queue(queue, self.persona_a)
        join_queue(queue, self.persona_b)
        next_entry = skip_speaker(queue, self.persona_a)
        self.assertIsNotNone(next_entry)
        self.assertEqual(next_entry.persona, self.persona_b)

    def test_get_active_queue_returns_none_when_no_queue(self):
        self.assertIsNone(get_active_queue(self.room))

    def test_clear_queue_on_scene_finish_closes_queue(self):
        scene = SceneFactory(location=self.room, is_active=True)
        queue = open_queue(self.room, self.persona_a)
        join_queue(queue, self.persona_a)
        clear_queue_on_scene_finish(scene)
        queue.refresh_from_db()
        self.assertFalse(queue.is_active)

    def test_clear_queue_on_scene_finish_noop_if_no_queue(self):
        scene = SceneFactory(location=self.room, is_active=True)
        # Should not raise
        clear_queue_on_scene_finish(scene)

    def test_remove_persona_from_room_queues_removes_entry(self):
        queue = open_queue(self.room, self.persona_a)
        join_queue(queue, self.persona_a)
        join_queue(queue, self.persona_b)
        remove_persona_from_room_queues(self.room, self.persona_a)
        self.assertEqual(queue_entries(queue).count(), 1)
        self.assertEqual(queue_entries(queue).first().persona, self.persona_b)

    def test_remove_persona_noop_if_no_queue(self):
        # Should not raise
        remove_persona_from_room_queues(self.room, self.persona_a)
