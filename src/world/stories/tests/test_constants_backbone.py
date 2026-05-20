from django.test import SimpleTestCase

from world.stories.constants import BeatKind, ProgressStatus, StoryMaturity, StoryScope


class BackboneConstantsTests(SimpleTestCase):
    def test_story_scope_has_unassigned(self):
        self.assertEqual(StoryScope.UNASSIGNED, "unassigned")
        self.assertIn(StoryScope.UNASSIGNED, StoryScope.values)

    def test_story_maturity_members(self):
        self.assertEqual(set(StoryMaturity.values), {"pitch", "outline", "plot"})

    def test_beat_kind_members(self):
        self.assertEqual(
            set(BeatKind.values),
            {"situation", "encounter", "task", "requirement"},
        )

    def test_progress_status_members(self):
        self.assertEqual(
            set(ProgressStatus.values),
            {"active", "waiting_for_gm", "resting", "completed"},
        )
