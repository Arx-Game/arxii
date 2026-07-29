"""Natural key tests for achievement content models (#2832).

Every model that enters CONTENT_MODELS must have NaturalKeyMixin with a
stable, non-pk natural key. These tests prove the composite-FK keys
round-trip through get_by_natural_key and serialize with natural FK keys
(no raw pks), which the export/import pipeline relies on.
"""

from django.core import serializers
from django.db import IntegrityError, transaction
from django.test import TestCase

from world.achievements.factories import (
    AchievementFactory,
    AchievementRequirementFactory,
    AchievementRewardFactory,
    ConditionStatRuleFactory,
    RewardDefinitionFactory,
)
from world.achievements.models import (
    Achievement,
    AchievementRequirement,
    AchievementReward,
    ConditionStatRule,
    RewardDefinition,
)


class AchievementSlugNaturalKeyTest(TestCase):
    """Achievement keys on slug (not name) — stable across display-name rewording."""

    def test_natural_key_is_slug(self):
        ach = AchievementFactory(slug="my-achievement", name="Display Name")
        self.assertEqual(ach.natural_key(), ("my-achievement",))

    def test_round_trip(self):
        ach = AchievementFactory(slug="round-trip-test")
        self.assertEqual(Achievement.objects.get_by_natural_key(*ach.natural_key()).pk, ach.pk)

    def test_serializes_with_natural_keys(self):
        ach = AchievementFactory(slug="serialize-test")
        data = serializers.serialize(
            "json", [ach], use_natural_foreign_keys=True, use_natural_primary_keys=True
        )
        self.assertIn('"slug": "serialize-test"', data)


class RewardDefinitionNaturalKeyTest(TestCase):
    def test_round_trip(self):
        reward = RewardDefinitionFactory(key="title.champion")
        self.assertEqual(
            RewardDefinition.objects.get_by_natural_key(*reward.natural_key()).pk,
            reward.pk,
        )

    def test_serializes_with_natural_keys(self):
        reward = RewardDefinitionFactory(key="title.serialize")
        data = serializers.serialize(
            "json", [reward], use_natural_foreign_keys=True, use_natural_primary_keys=True
        )
        self.assertNotIn(f'"pk": {reward.pk}', data)


class AchievementRequirementNaturalKeyTest(TestCase):
    def test_round_trip(self):
        req = AchievementRequirementFactory()
        self.assertEqual(
            AchievementRequirement.objects.get_by_natural_key(*req.natural_key()).pk,
            req.pk,
        )

    def test_duplicate_raises_integrity_error(self):
        req = AchievementRequirementFactory()
        with self.assertRaises(IntegrityError), transaction.atomic():
            AchievementRequirement.objects.create(
                achievement=req.achievement,
                stat=req.stat,
                threshold=req.threshold,
                comparison=req.comparison,
            )


class AchievementRewardNaturalKeyTest(TestCase):
    def test_round_trip(self):
        award = AchievementRewardFactory()
        self.assertEqual(
            AchievementReward.objects.get_by_natural_key(*award.natural_key()).pk,
            award.pk,
        )

    def test_duplicate_raises_integrity_error(self):
        award = AchievementRewardFactory()
        with self.assertRaises(IntegrityError), transaction.atomic():
            AchievementReward.objects.create(
                achievement=award.achievement,
                reward=award.reward,
            )


class ConditionStatRuleNaturalKeyTest(TestCase):
    def test_round_trip(self):
        rule = ConditionStatRuleFactory()
        self.assertEqual(
            ConditionStatRule.objects.get_by_natural_key(*rule.natural_key()).pk,
            rule.pk,
        )
