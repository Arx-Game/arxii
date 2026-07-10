"""Tests for the GMRewardConfig singleton + award_gm_story_reward service (#2123)."""

from unittest.mock import patch

from django.test import TestCase

from world.gm.factories import GMProfileFactory
from world.gm.models import GMRewardConfig, GMWeeklyRewardTracker
from world.gm.services import award_gm_story_reward
from world.progression.models import XPTransaction
from world.progression.types import ProgressionReason


class GMRewardConfigSingletonTests(TestCase):
    """The config is a lazily-created pk=1 singleton with the spec's defaults."""

    def test_load_creates_row_with_recommended_defaults(self) -> None:
        self.assertFalse(GMRewardConfig.objects.exists())
        config = GMRewardConfig.load()
        self.assertEqual(config.pk, 1)
        self.assertEqual(config.beat_xp_per_player, 6)
        self.assertEqual(config.beat_xp_cap, 48)
        self.assertEqual(config.episode_xp_per_player, 15)
        self.assertEqual(config.episode_xp_cap, 120)
        self.assertEqual(config.story_completion_xp_per_player, 25)
        self.assertEqual(config.story_completion_xp_cap, 200)
        self.assertEqual(config.weekly_reward_cap, 300)
        self.assertEqual(config.feedback_xp_per_rating_point, 5)

    def test_load_is_idempotent(self) -> None:
        first = GMRewardConfig.load()
        second = GMRewardConfig.load()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(GMRewardConfig.objects.count(), 1)


class AwardGmStoryRewardTests(TestCase):
    """award_gm_story_reward: players-served scaling, event cap, weekly ceiling."""

    def test_awards_per_player_xp_scaled_by_players_served(self) -> None:
        gm = GMProfileFactory()
        award_gm_story_reward(
            gm_profile=gm,
            players_served=3,
            per_player_xp=6,
            event_cap=48,
            description="test award",
        )
        txn = XPTransaction.objects.get(account=gm.account)
        self.assertEqual(txn.amount, 18)
        self.assertEqual(txn.reason, ProgressionReason.GM_STORY_REWARD)
        self.assertEqual(txn.description, "test award")

    def test_event_cap_truncates_before_weekly_cap(self) -> None:
        gm = GMProfileFactory()
        award_gm_story_reward(
            gm_profile=gm,
            players_served=8,
            per_player_xp=25,
            event_cap=120,
            description="capped award",
        )
        txn = XPTransaction.objects.get(account=gm.account)
        # 8 * 25 = 200, but event_cap truncates to 120.
        self.assertEqual(txn.amount, 120)

    def test_weekly_ceiling_truncates_a_later_award(self) -> None:
        gm = GMProfileFactory()
        config = GMRewardConfig.load()
        config.weekly_reward_cap = 20
        config.save(update_fields=["weekly_reward_cap"])

        award_gm_story_reward(
            gm_profile=gm, players_served=1, per_player_xp=15, event_cap=120, description="first"
        )
        award_gm_story_reward(
            gm_profile=gm, players_served=1, per_player_xp=15, event_cap=120, description="second"
        )

        amounts = list(
            XPTransaction.objects.filter(account=gm.account)
            .order_by("pk")
            .values_list("amount", flat=True)
        )
        self.assertEqual(amounts, [15, 5])
        tracker = GMWeeklyRewardTracker.objects.get(gm_profile=gm)
        self.assertEqual(tracker.xp_awarded_this_week, 20)

    def test_weekly_ceiling_exhausted_is_a_noop_not_an_error(self) -> None:
        gm = GMProfileFactory()
        config = GMRewardConfig.load()
        config.weekly_reward_cap = 10
        config.save(update_fields=["weekly_reward_cap"])

        award_gm_story_reward(
            gm_profile=gm, players_served=1, per_player_xp=10, event_cap=120, description="first"
        )
        result = award_gm_story_reward(
            gm_profile=gm, players_served=1, per_player_xp=10, event_cap=120, description="second"
        )
        self.assertIsNone(result)
        self.assertEqual(XPTransaction.objects.filter(account=gm.account).count(), 1)

    def test_zero_players_served_is_a_noop(self) -> None:
        gm = GMProfileFactory()
        result = award_gm_story_reward(
            gm_profile=gm, players_served=0, per_player_xp=6, event_cap=48, description="nothing"
        )
        self.assertIsNone(result)
        self.assertFalse(XPTransaction.objects.filter(account=gm.account).exists())

    def test_config_value_change_is_reflected_in_award(self) -> None:
        """Code reads the config row, never a module constant."""
        gm = GMProfileFactory()
        config = GMRewardConfig.load()
        config.beat_xp_cap = 999
        config.weekly_reward_cap = 999
        config.save(update_fields=["beat_xp_cap", "weekly_reward_cap"])

        award_gm_story_reward(
            gm_profile=gm,
            players_served=1000,
            per_player_xp=6,
            event_cap=config.beat_xp_cap,
            description="retuned cap",
        )
        txn = XPTransaction.objects.get(account=gm.account)
        self.assertEqual(txn.amount, 999)

    def test_failure_isolation_never_raises(self) -> None:
        """A bug in the underlying award_xp call must never propagate."""
        gm = GMProfileFactory()
        with patch(
            "world.progression.services.awards.award_xp",
            side_effect=RuntimeError("boom"),
        ):
            result = award_gm_story_reward(
                gm_profile=gm,
                players_served=1,
                per_player_xp=6,
                event_cap=48,
                description="should not raise",
            )
        self.assertIsNone(result)
