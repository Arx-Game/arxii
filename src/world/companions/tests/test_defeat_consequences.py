"""Tests for companion defeat consequence gating (#1873)."""

from django.test import TestCase

from world.combat.constants import RiskLevel
from world.companions.factories import CompanionFactory
from world.companions.services import resolve_companion_defeat


class CompanionDefeatConsequenceTests(TestCase):
    def test_low_risk_defeat_leaves_companion_active(self):
        companion = CompanionFactory()
        died = resolve_companion_defeat(companion, RiskLevel.LOW)
        companion.refresh_from_db()
        self.assertFalse(died)
        self.assertTrue(companion.is_active)

    def test_moderate_risk_defeat_leaves_companion_active(self):
        companion = CompanionFactory()
        died = resolve_companion_defeat(companion, RiskLevel.MODERATE)
        companion.refresh_from_db()
        self.assertFalse(died)
        self.assertTrue(companion.is_active)

    def test_high_risk_defeat_leaves_companion_active(self):
        companion = CompanionFactory()
        died = resolve_companion_defeat(companion, RiskLevel.HIGH)
        companion.refresh_from_db()
        self.assertFalse(died)
        self.assertTrue(companion.is_active)

    def test_extreme_risk_defeat_resolves_without_error(self):
        """At EXTREME/LETHAL, the pool draws recover/incapacitated/die.

        We can't assert a specific draw (it's random), but the companion
        should either survive (is_active True) or be released (is_active False)
        — not raise an exception.
        """
        companion = CompanionFactory()
        resolve_companion_defeat(companion, RiskLevel.EXTREME)
        companion.refresh_from_db()
        # Either outcome is valid; what matters is no exception.
        self.assertIn(companion.is_active, [True, False])

    def test_lethal_risk_defeat_resolves_without_error(self):
        companion = CompanionFactory()
        resolve_companion_defeat(companion, RiskLevel.LETHAL)
        companion.refresh_from_db()
        self.assertIn(companion.is_active, [True, False])

    def test_lethal_risk_can_release_companion(self):
        """Run enough lethal draws that at least one releases a companion.

        The die weight is 1 out of 6 total (2+3+1), so P(die) ≈ 1/6 per draw.
        With 50 draws, P(no death) = (5/6)^50 ≈ 0.0001 — effectively zero.
        """
        released_count = 0
        for _ in range(50):
            companion = CompanionFactory()
            died = resolve_companion_defeat(companion, RiskLevel.LETHAL)
            if died:
                released_count += 1
                companion.refresh_from_db()
                self.assertFalse(companion.is_active)
                self.assertIsNotNone(companion.released_at)
        self.assertGreater(released_count, 0)
