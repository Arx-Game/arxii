from django.test import TestCase

from world.stories.constants import (
    BeatKind,
    ProgressStatus,
    StoryMaturity,
    StoryScope,
)
from world.stories.factories import (
    BeatFactory,
    EpisodeFactory,
    StoryFactory,
    StoryProgressFactory,
)
from world.stories.models import Story, StoryNote


class BackboneModelDefaultsTests(TestCase):
    def test_new_story_defaults_unassigned_and_pitch(self):
        story = Story.objects.create(title="t", description="d")
        self.assertEqual(story.scope, StoryScope.UNASSIGNED)
        self.assertEqual(story.maturity, StoryMaturity.PITCH)

    def test_chapter_and_episode_default_pitch(self):
        episode = EpisodeFactory()
        self.assertEqual(episode.maturity, StoryMaturity.PITCH)
        self.assertEqual(episode.chapter.maturity, StoryMaturity.PITCH)
        self.assertEqual(episode.resting_conclusion, "")
        self.assertFalse(episode.is_ending)

    def test_beat_backbone_field_defaults(self):
        beat = BeatFactory()
        self.assertEqual(beat.kind, BeatKind.TASK)
        self.assertTrue(beat.advances)
        self.assertEqual(beat.risk, 0)

    def test_progress_status_defaults_active(self):
        progress = StoryProgressFactory()
        self.assertEqual(progress.status, ProgressStatus.ACTIVE)
        self.assertTrue(progress.is_active)

    def test_story_note_is_append_record(self):
        story = StoryFactory()
        note = StoryNote.objects.create(story=story, body="future idea")
        self.assertEqual(note.story, story)
        self.assertIsNotNone(note.created_at)
        self.assertIsNone(note.author_account)

    def test_story_note_factory(self):
        from world.stories.factories import StoryNoteFactory

        note = StoryNoteFactory()
        self.assertTrue(note.body)
        self.assertIsNotNone(note.story_id)
