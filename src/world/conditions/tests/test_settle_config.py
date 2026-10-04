from django.test import TestCase

from world.conditions.services import get_settle_config


class SettleConfigTests(TestCase):
    def test_singleton_created_lazily_with_defaults(self):
        cfg = get_settle_config()
        self.assertEqual(cfg.pk, 1)
        self.assertEqual(cfg.settled_seconds_per_round, 300)
        self.assertEqual(cfg.lapse_warning_seconds, 300)
        self.assertEqual(get_settle_config().pk, 1)
