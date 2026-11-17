"""Tests for contribute_to_technique_progress service (#2711)."""

from unittest.mock import patch

from django.test import TestCase

from world.action_points.models import ActionPointPool
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import CharacterAuraFactory, TechniqueFactory
from world.magic.models import (
    Affinity,
    CharacterTechnique,
    TechniqueProgress,
    TechniqueProgressWeekly,
)
from world.magic.services.technique_progress import contribute_to_technique_progress
from world.seeds.modifier_values import seed_pool_and_cap_lanes


class ContributeToProgressTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        seed_pool_and_cap_lanes()

    def setUp(self):
        self.sheet = CharacterSheetFactory()
        self.technique = TechniqueFactory()
        self.pool = ActionPointPool.get_or_create_for_character(self.sheet.character)
        self.pool.current = 500
        self.pool.save()
        # Give the character the gift + a GIFT thread so learn_technique's
        # gift-owned check and technique cap check both pass.
        from world.magic.constants import TargetKind
        from world.magic.factories import ResonanceFactory
        from world.magic.models import CharacterGift, Thread

        CharacterGift.objects.create(character=self.sheet, gift=self.technique.gift)
        Thread.objects.create(
            owner=self.sheet,
            resonance=ResonanceFactory(),
            target_kind=TargetKind.GIFT,
            target_gift=self.technique.gift,
            level=0,
        )
        self.progress = TechniqueProgress.objects.create(
            character_sheet=self.sheet,
            technique=self.technique,
            total_required=50,
            source="gift_acquisition",
        )

    def test_contribution_adds_points(self):
        result = contribute_to_technique_progress(self.sheet, self.progress, dev_points=20)
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.points_accumulated, 20)
        self.assertIsNone(result)

    def test_the_learn_rate_scales_the_meter_once_and_not_the_cap_or_the_cost(self):
        CharacterAuraFactory(character=self.sheet, celestial=0, primal=20, abyssal=80)
        affinity = Affinity.objects.get(name="Abyssal")
        affinity.learn_rate_percent = 150
        affinity.save()
        contribute_to_technique_progress(self.sheet, self.progress, dev_points=20)
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.points_accumulated, 30)
        weekly = TechniqueProgressWeekly.objects.get(
            character_sheet=self.sheet, technique=self.technique
        )
        self.assertEqual(weekly.points_contributed, 20)
        self.pool.refresh_from_db()
        self.assertEqual(self.pool.current, 480)

    def test_a_trial_award_is_never_scaled_down_to_nothing_by_a_slow_learn_rate(self):
        from world.checks.constants import EffectType
        from world.checks.factories import ConsequenceEffectFactory
        from world.checks.types import ResolutionContext
        from world.mechanics.effect_handlers import _technique_training

        CharacterAuraFactory(character=self.sheet, celestial=0, primal=20, abyssal=80)
        affinity = Affinity.objects.get(name="Abyssal")
        affinity.learn_rate_percent = 50
        affinity.save()
        effect = ConsequenceEffectFactory(
            effect_type=EffectType.TECHNIQUE_TRAINING,
            technique=self.technique,
            training_points=1,
            training_meter_size=10,
        )

        _technique_training(effect, ResolutionContext(character=self.sheet.character))

        # 1 point at 50% is 0 by integer arithmetic; the learner still gets 1.
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.points_accumulated, 1)

    def test_contribution_spends_ap(self):
        contribute_to_technique_progress(self.sheet, self.progress, dev_points=20)
        self.pool.refresh_from_db()
        self.assertEqual(self.pool.current, 480)

    def test_contribution_creates_weekly_tracker(self):
        contribute_to_technique_progress(self.sheet, self.progress, dev_points=20)
        weekly = TechniqueProgressWeekly.objects.get(
            character_sheet=self.sheet,
            technique=self.technique,
        )
        self.assertEqual(weekly.points_contributed, 20)

    def test_completion_mints_technique(self):
        result = contribute_to_technique_progress(self.sheet, self.progress, dev_points=50)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, CharacterTechnique)
        self.assertFalse(TechniqueProgress.objects.filter(pk=self.progress.pk).exists())

    def test_partial_then_complete(self):
        result = contribute_to_technique_progress(self.sheet, self.progress, dev_points=30)
        self.assertIsNone(result)
        self.progress.refresh_from_db()
        result = contribute_to_technique_progress(self.sheet, self.progress, dev_points=20)
        self.assertIsNotNone(result)

    def test_weekly_cap_exceeded(self):
        # Default cap is 50; contribute 50 (completes the meter)
        contribute_to_technique_progress(self.sheet, self.progress, dev_points=50)
        # Meter is complete and deleted; create a new one with higher total
        progress2 = TechniqueProgress.objects.create(
            character_sheet=self.sheet,
            technique=self.technique,
            total_required=200,
            source="gift_acquisition",
        )
        from world.magic.exceptions import WeeklyTrainingCapExceeded

        with self.assertRaises(WeeklyTrainingCapExceeded):
            contribute_to_technique_progress(self.sheet, progress2, dev_points=51)

    def test_unbound_surcharge_increases_ap_not_points(self):
        """With a +50% surcharge, 20 points costs 30 AP."""
        with patch(
            "world.magic.services.technique_progress.magic_learning_ap_cost_surcharge_percent",
            return_value=50,
        ):
            contribute_to_technique_progress(self.sheet, self.progress, dev_points=20)
        self.pool.refresh_from_db()
        self.assertEqual(self.pool.current, 470)  # 500 - ceil(20 * 1.5)
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.points_accumulated, 20)

    def test_ap_to_spend_decoupled_from_dev_points(self):
        """When ap_to_spend is set, AP spent != dev_points credited."""
        contribute_to_technique_progress(self.sheet, self.progress, dev_points=0, ap_to_spend=20)
        self.pool.refresh_from_db()
        self.assertEqual(self.pool.current, 480)  # 500 - 20 AP
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.points_accumulated, 0)  # 0 dev points

    def test_botch_spends_ap_zero_dev_points(self):
        """A botched check: full AP spent, 0 dev points credited."""
        contribute_to_technique_progress(self.sheet, self.progress, dev_points=0, ap_to_spend=20)
        self.pool.refresh_from_db()
        self.assertEqual(self.pool.current, 480)
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.points_accumulated, 0)
        # Weekly tracker still records 0 dev points
        weekly = TechniqueProgressWeekly.objects.get(
            character_sheet=self.sheet, technique=self.technique
        )
        self.assertEqual(weekly.points_contributed, 0)
