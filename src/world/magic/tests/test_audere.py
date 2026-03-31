"""Tests for Audere threshold and lifecycle."""

from django.test import TestCase

from world.conditions.factories import ConditionStageFactory, ConditionTemplateFactory
from world.magic.factories import AudereThresholdFactory, IntensityTierFactory


class AudereThresholdModelTests(TestCase):
    """Test AudereThreshold configuration model."""

    def test_create_threshold(self) -> None:
        condition = ConditionTemplateFactory(has_progression=True)
        stage = ConditionStageFactory(condition=condition, stage_order=3)
        tier = IntensityTierFactory(name="Major", threshold=15)
        threshold = AudereThresholdFactory(
            minimum_intensity_tier=tier,
            minimum_warp_stage=stage,
            intensity_bonus=25,
            anima_pool_bonus=40,
            warp_multiplier=3,
        )
        assert threshold.intensity_bonus == 25
        assert threshold.anima_pool_bonus == 40
        assert threshold.warp_multiplier == 3
        assert threshold.minimum_intensity_tier == tier
        assert threshold.minimum_warp_stage == stage
