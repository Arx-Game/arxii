"""Tests for the 3 sanctum ritual outcome-tier award models (#1207)."""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from world.magic.models.sanctum import (
    SanctumDissolutionRecoveryAward,
    SanctumHomecomingGainAward,
    SanctumPurgingRetentionAward,
)
from world.traits.factories import CheckOutcomeFactory


class SanctumAwardModelsTests(TestCase):
    def test_homecoming_gain_award(self):
        outcome = CheckOutcomeFactory(success_level=2)
        SanctumHomecomingGainAward.objects.create(
            outcome_tier=outcome, gain_multiplier=Decimal("1.25")
        )
        fetched = SanctumHomecomingGainAward.objects.get(outcome_tier=outcome)
        self.assertEqual(fetched.gain_multiplier, Decimal("1.25"))

    def test_purging_retention_award_accepts_negative(self):
        outcome = CheckOutcomeFactory(success_level=-1)
        SanctumPurgingRetentionAward.objects.create(
            outcome_tier=outcome, retention_modifier=Decimal("-0.150")
        )
        fetched = SanctumPurgingRetentionAward.objects.get(outcome_tier=outcome)
        self.assertEqual(fetched.retention_modifier, Decimal("-0.150"))

    def test_dissolution_recovery_award(self):
        outcome = CheckOutcomeFactory(success_level=1)
        SanctumDissolutionRecoveryAward.objects.create(
            outcome_tier=outcome, recovery_fraction=Decimal("0.50")
        )
        fetched = SanctumDissolutionRecoveryAward.objects.get(outcome_tier=outcome)
        self.assertEqual(fetched.recovery_fraction, Decimal("0.50"))
