from django.test import TestCase

from world.scenes.constants import SceneRoundMode, SceneRoundStartReason
from world.scenes.factories import SceneRoundFactory
from world.scenes.models import get_scene_round_defaults_config


class SceneRoundModeTests(TestCase):
    def test_config_singleton_defaults(self):
        cfg = get_scene_round_defaults_config()
        self.assertEqual(cfg.pk, 1)
        self.assertEqual(cfg.default_mode, SceneRoundMode.POSE_ORDER)
        self.assertEqual(cfg.advance_quorum_pct, 60)
        self.assertEqual(cfg.max_actions_per_round, 1)
        self.assertFalse(cfg.per_target_repeat_lock)
        self.assertGreaterEqual(cfg.anti_spam_seconds, 5)

    def test_get_config_is_idempotent(self):
        a = get_scene_round_defaults_config()
        b = get_scene_round_defaults_config()
        self.assertEqual(a.pk, b.pk)

    def test_start_reason_no_longer_forces_a_mode(self):
        # #1466: start_reason and mode are fully orthogonal — the model no longer rewrites
        # mode from start_reason. Danger rounds become STRICT only via
        # ensure_round_for_acute_condition, not the persistence layer.
        rnd = SceneRoundFactory(
            start_reason=SceneRoundStartReason.DANGER, mode=SceneRoundMode.STRICT
        )
        self.assertEqual(rnd.mode, SceneRoundMode.STRICT)

    def test_policy_columns_default_from_config(self):
        rnd = SceneRoundFactory()
        self.assertEqual(rnd.advance_quorum_pct, 60)
        self.assertEqual(rnd.max_actions_per_round, 1)
