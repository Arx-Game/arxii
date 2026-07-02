"""Service tests for the stakes contract engine (#1770 PR1)."""

from django.test import TestCase

from world.societies.constants import RenownRisk
from world.stories.services.stakes import compute_effective_risk


class ComputeEffectiveRiskTests(TestCase):
    def test_none_stays_none(self):
        self.assertEqual(compute_effective_risk(RenownRisk.NONE, 4, 10), RenownRisk.NONE)

    def test_at_level_keeps_declared(self):
        self.assertEqual(compute_effective_risk(RenownRisk.EXTREME, 4, 4), RenownRisk.EXTREME)

    def test_overleveled_decays_one_tier_per_two_levels(self):
        self.assertEqual(compute_effective_risk(RenownRisk.EXTREME, 4, 6), RenownRisk.HIGH)
        self.assertEqual(compute_effective_risk(RenownRisk.EXTREME, 4, 10), RenownRisk.LOW)

    def test_grossly_overleveled_hits_none(self):
        self.assertEqual(compute_effective_risk(RenownRisk.HIGH, 4, 12), RenownRisk.NONE)

    def test_underleveled_upgrade_is_capped_at_one_tier(self):
        self.assertEqual(compute_effective_risk(RenownRisk.MODERATE, 6, 2), RenownRisk.HIGH)

    def test_upgrade_never_exceeds_extreme(self):
        self.assertEqual(compute_effective_risk(RenownRisk.EXTREME, 6, 2), RenownRisk.EXTREME)
