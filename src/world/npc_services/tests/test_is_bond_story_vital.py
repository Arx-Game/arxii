"""Tests for is_bond_story_vital — the derived 'vital to your story' read (#2039)."""

from django.test import TestCase

from world.npc_services.factories import NpcRegardFactory
from world.npc_services.regard import get_regard_event_config, is_bond_story_vital


class IsBondStoryVitalTests(TestCase):
    def test_below_threshold_is_not_vital(self):
        regard = NpcRegardFactory(value=50)
        self.assertFalse(is_bond_story_vital(regard))

    def test_strongly_negative_is_vital(self):
        regard = NpcRegardFactory(value=-250)
        self.assertTrue(is_bond_story_vital(regard))

    def test_strongly_positive_is_vital(self):
        regard = NpcRegardFactory(value=250)
        self.assertTrue(is_bond_story_vital(regard))

    def test_exactly_at_threshold_is_vital(self):
        cfg = get_regard_event_config()
        regard = NpcRegardFactory(value=cfg.story_vital_threshold)
        self.assertTrue(is_bond_story_vital(regard))
