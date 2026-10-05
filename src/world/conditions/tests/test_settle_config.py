from django.test import TestCase

from world.conditions.services import get_settle_config


class SettleConfigTests(TestCase):
    def test_singleton_created_lazily_with_defaults(self):
        cfg = get_settle_config()
        self.assertEqual(cfg.pk, 1)
        self.assertEqual(cfg.settled_seconds_per_round, 300)
        self.assertEqual(cfg.lapse_warning_seconds, 300)
        self.assertEqual(get_settle_config().pk, 1)

    def test_zero_rejected_for_both_fields(self):
        from django.core.exceptions import ValidationError

        cfg = get_settle_config()
        for field in ("settled_seconds_per_round", "lapse_warning_seconds"):
            with self.subTest(field=field):
                setattr(cfg, field, 0)
                with self.assertRaises(ValidationError) as ctx:
                    cfg.full_clean()
                self.assertIn(field, ctx.exception.message_dict)
                setattr(cfg, field, 300)
