"""Tests for the RegardEventConfig singleton and its accessor."""

from django.test import TestCase

from world.npc_services.models import RegardEventConfig
from world.npc_services.regard import get_regard_event_config


class RegardEventConfigTests(TestCase):
    def test_get_regard_event_config_creates_singleton(self):
        self.assertEqual(RegardEventConfig.objects.count(), 0)
        cfg = get_regard_event_config()
        self.assertEqual(cfg.pk, 1)
        self.assertEqual(RegardEventConfig.objects.count(), 1)

    def test_get_regard_event_config_returns_existing(self):
        first = get_regard_event_config()
        second = get_regard_event_config()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(RegardEventConfig.objects.count(), 1)

    def test_defaults(self):
        cfg = get_regard_event_config()
        self.assertEqual(cfg.max_event_delta, 100)
        self.assertEqual(cfg.combat_defeat_amount, -15)
        self.assertEqual(cfg.combat_harm_amount, -15)
        self.assertEqual(cfg.story_vital_threshold, 200)
