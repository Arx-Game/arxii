"""Shared Audere gate fixture for the offer-surface test modules (#873).

Imported by the magic offer-surface/API tests, the combat cleanup tests, and
the integration pipeline test so they all open the eligibility gate the same
way.
"""

from dataclasses import dataclass

from world.conditions.factories import (
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.conditions.models import ConditionStage, ConditionTemplate
from world.magic.audere import SOULFRAY_CONDITION_NAME, AudereThreshold
from world.magic.factories import (
    AudereThresholdFactory,
    IntensityTierFactory,
    wire_audere_power_multipliers,
)
from world.magic.models import IntensityTier


@dataclass(frozen=True)
class AudereGateFixture:
    """Authored rows that open the Audere eligibility gate (shared by test classes)."""

    soulfray_template: ConditionTemplate
    soulfray_stage: ConditionStage
    minor_tier: IntensityTier
    major_tier: IntensityTier
    threshold: AudereThreshold


def build_audere_gate_fixture(*, tier_suffix: str) -> AudereGateFixture:
    """Seed Soulfray stages, IntensityTiers, and the AudereThreshold gate config.

    ``tier_suffix`` keeps IntensityTier names distinct per test class so
    SharedMemoryModel identity-map caching never hands one class another's rows.
    """
    wire_audere_power_multipliers()

    soulfray_template = ConditionTemplateFactory(name=SOULFRAY_CONDITION_NAME, has_progression=True)
    ConditionStageFactory(condition=soulfray_template, stage_order=1, name="Fraying")
    ConditionStageFactory(condition=soulfray_template, stage_order=2, name="Tearing")
    soulfray_stage = ConditionStageFactory(
        condition=soulfray_template, stage_order=3, name="Ripping"
    )

    minor_tier = IntensityTierFactory(name=f"Minor_{tier_suffix}", threshold=1, control_modifier=0)
    major_tier = IntensityTierFactory(
        name=f"Major_{tier_suffix}", threshold=15, control_modifier=-5
    )
    threshold = AudereThresholdFactory(
        minimum_intensity_tier=major_tier,
        minimum_warp_stage=soulfray_stage,
        intensity_bonus=20,
        anima_pool_bonus=30,
        warp_multiplier=2,
    )
    return AudereGateFixture(
        soulfray_template=soulfray_template,
        soulfray_stage=soulfray_stage,
        minor_tier=minor_tier,
        major_tier=major_tier,
        threshold=threshold,
    )
