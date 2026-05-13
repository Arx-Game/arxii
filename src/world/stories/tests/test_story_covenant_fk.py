"""Tests for Story.covenant FK and Beat consequence pool FKs."""

from django.test import TestCase

from actions.factories import ConsequencePoolFactory
from world.covenants.factories import CovenantFactory
from world.stories.factories import BeatFactory, StoryFactory
from world.stories.models import Story


class StoryCovenantFKTests(TestCase):
    def test_story_can_link_covenant(self) -> None:
        c = CovenantFactory()
        s = StoryFactory(covenant=c)
        self.assertEqual(s.covenant, c)
        self.assertIn(s, c.storylines.all())

    def test_set_null_on_covenant_delete(self) -> None:
        c = CovenantFactory()
        s = StoryFactory(covenant=c)
        story_pk = s.pk
        c.delete()
        # Bypass SharedMemoryModel identity map via .values() to get the raw DB value.
        row = Story.objects.filter(pk=story_pk).values("covenant_id").first()
        self.assertIsNotNone(row, "Story must survive covenant deletion")
        self.assertIsNone(row["covenant_id"])

    def test_default_covenant_is_null(self) -> None:
        s = StoryFactory()
        self.assertIsNone(s.covenant)


class BeatConsequenceFKTests(TestCase):
    def test_beat_consequence_fks_default_null(self) -> None:
        beat = BeatFactory()
        self.assertIsNone(beat.success_consequences)
        self.assertIsNone(beat.failure_consequences)
        self.assertIsNone(beat.expired_consequences)

    def test_beat_can_link_consequence_pools(self) -> None:
        pool = ConsequencePoolFactory()
        beat = BeatFactory(success_consequences=pool)
        self.assertEqual(beat.success_consequences, pool)
        self.assertIn(beat, pool.success_beats.all())
