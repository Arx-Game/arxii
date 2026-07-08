"""Tests for touch_gm_activity + activity stamping from GM verbs (#2004)."""

from django.test import TestCase

from world.gm.factories import GMProfileFactory, GMTableFactory
from world.gm.services import surrender_character_story, touch_gm_activity
from world.stories.factories import StoryFactory


class TouchGmActivityTests(TestCase):
    def test_stamps_last_active_at(self) -> None:
        gm = GMProfileFactory()
        self.assertIsNone(gm.last_active_at)
        touch_gm_activity(gm)
        gm.refresh_from_db()
        self.assertIsNotNone(gm.last_active_at)

    def test_is_idempotent_and_updates(self) -> None:
        gm = GMProfileFactory()
        touch_gm_activity(gm)
        first = gm.last_active_at
        touch_gm_activity(gm)
        gm.refresh_from_db()
        self.assertGreaterEqual(gm.last_active_at, first)


class SurrenderStampsActivityTests(TestCase):
    def test_surrender_stamps_gm_activity(self) -> None:
        gm = GMProfileFactory()
        table = GMTableFactory(gm=gm)
        story = StoryFactory(primary_table=table)
        self.assertIsNone(gm.last_active_at)
        surrender_character_story(gm, story)
        gm.refresh_from_db()
        self.assertIsNotNone(gm.last_active_at)
