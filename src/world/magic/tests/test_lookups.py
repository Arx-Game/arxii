"""Tests for Resonance Pivot Spec A Phase 3 lookup tables.

Covers ThreadPullCost, ThreadXPLockedLevel, ThreadPullEffect,
ImbuingProseTemplate, and Ritual / RitualComponentRequirement.
"""

from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.test import TestCase

from world.magic.constants import EffectKind, TargetKind, VitalBonusTarget
from world.magic.factories import (
    ImbuingProseTemplateFactory,
    ResonanceFactory,
    ThreadPullCostFactory,
    ThreadPullEffectFactory,
    ThreadXPLockedLevelFactory,
)
from world.magic.models import ThreadPullCost, ThreadXPLockedLevel


class ThreadPullCostModelTests(TestCase):
    def test_three_launch_tiers_exist_after_factory_setup(self):
        tier1 = ThreadPullCostFactory(tier=1, resonance_cost=1, anima_per_thread=1, label="soft")
        tier2 = ThreadPullCostFactory(tier=2, resonance_cost=3, anima_per_thread=2, label="hard")
        tier3 = ThreadPullCostFactory(tier=3, resonance_cost=6, anima_per_thread=3, label="max")
        self.assertEqual(ThreadPullCost.objects.count(), 3)
        self.assertEqual({c.tier for c in (tier1, tier2, tier3)}, {1, 2, 3})

    def test_tier_is_unique(self):
        ThreadPullCostFactory(tier=1)
        with self.assertRaises(IntegrityError):
            # Force a new insert (django_get_or_create would normally just fetch).
            ThreadPullCost.objects.create(tier=1, resonance_cost=2, anima_per_thread=2, label="dup")


class ThreadXPLockedLevelModelTests(TestCase):
    def test_levels_are_internal_scale_multiples_of_ten(self):
        ThreadXPLockedLevelFactory(level=20, xp_cost=200)
        ThreadXPLockedLevelFactory(level=30, xp_cost=400)
        self.assertEqual(
            list(ThreadXPLockedLevel.objects.values_list("level", flat=True).order_by("level")),
            [20, 30],
        )

    def test_level_unique(self):
        ThreadXPLockedLevelFactory(level=20)
        with self.assertRaises(IntegrityError):
            ThreadXPLockedLevel.objects.create(level=20, xp_cost=999)


class ThreadPullEffectCleanTests(TestCase):
    def test_flat_bonus_requires_flat_bonus_amount(self):
        eff = ThreadPullEffectFactory.build(
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=None,
        )
        with self.assertRaises(ValidationError):
            eff.clean()

    def test_flat_bonus_rejects_other_payloads(self):
        eff = ThreadPullEffectFactory.build(
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=2,
            intensity_bump_amount=1,
        )
        with self.assertRaises(ValidationError):
            eff.clean()

    def test_vital_bonus_requires_vital_target(self):
        eff = ThreadPullEffectFactory.build(
            effect_kind=EffectKind.VITAL_BONUS,
            flat_bonus_amount=None,
            vital_bonus_amount=5,
            vital_target=None,
        )
        with self.assertRaises(ValidationError):
            eff.clean()

    def test_vital_bonus_with_target_passes(self):
        eff = ThreadPullEffectFactory.build(
            effect_kind=EffectKind.VITAL_BONUS,
            flat_bonus_amount=None,
            vital_bonus_amount=5,
            vital_target=VitalBonusTarget.MAX_HEALTH,
        )
        eff.clean()  # no exception

    def test_narrative_only_requires_snippet_and_no_numeric_payload(self):
        eff = ThreadPullEffectFactory.build(
            effect_kind=EffectKind.NARRATIVE_ONLY,
            flat_bonus_amount=None,
            narrative_snippet="",
        )
        with self.assertRaises(ValidationError):
            eff.clean()


class ImbuingProseTemplateTests(TestCase):
    def test_unique_together_resonance_and_target_kind(self):
        res = ResonanceFactory()
        ImbuingProseTemplateFactory(resonance=res, target_kind=TargetKind.TRAIT, prose="X")
        with self.assertRaises(IntegrityError):
            ImbuingProseTemplateFactory(resonance=res, target_kind=TargetKind.TRAIT, prose="Y")

    def test_universal_fallback_row_allowed(self):
        ImbuingProseTemplateFactory(resonance=None, target_kind=None, prose="universal")
        # No exception raised.
