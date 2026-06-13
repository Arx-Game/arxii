from decimal import Decimal

from django.test import TestCase

from world.combat.clash import outcome_to_delta
from world.combat.factories import ClashConfigFactory
from world.traits.factories import CheckOutcomeFactory


class OutcomeToDeltaTests(TestCase):
    """Tests for the power-scaled outcome_to_delta formula.

    New signature: outcome_to_delta(*, check_outcome, power, config)

    Formula:
      - botch (level <= -2): -round(power * botch_backfire_fraction * power_scale)
      - all others:           round(power * quality_multiplier_for(level) * power_scale)

    Default ClashConfig values used for the table below:
      power_scale              = 0.5
      quality_multiplier_critical = 1.5   (level >= 3)
      quality_multiplier_great    = 1.25  (level == 2)
      quality_multiplier_success  = 1.0   (level == 1)
      quality_multiplier_partial  = 0.5   (level == 0)
      quality_multiplier_failure  = 0.0   (level <= -1)
      botch_backfire_fraction  = 0.5
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.config = ClashConfigFactory()

    def test_critical_success(self) -> None:
        """level >= 3, power=40 → round(40 * 1.5 * 0.5) = 30."""
        outcome = CheckOutcomeFactory(success_level=3)
        result = outcome_to_delta(check_outcome=outcome, power=40, config=self.config)
        expected = round(40 * Decimal("1.5") * Decimal("0.5"))
        self.assertEqual(result, expected)
        self.assertEqual(result, 30)

    def test_great_success(self) -> None:
        """level == 2, power=40 → round(40 * 1.25 * 0.5) = 25."""
        outcome = CheckOutcomeFactory(success_level=2)
        result = outcome_to_delta(check_outcome=outcome, power=40, config=self.config)
        expected = round(40 * Decimal("1.25") * Decimal("0.5"))
        self.assertEqual(result, expected)
        self.assertEqual(result, 25)

    def test_success(self) -> None:
        """level == 1, power=40 → round(40 * 1.0 * 0.5) = 20."""
        outcome = CheckOutcomeFactory(success_level=1)
        result = outcome_to_delta(check_outcome=outcome, power=40, config=self.config)
        expected = round(40 * Decimal("1.0") * Decimal("0.5"))
        self.assertEqual(result, expected)
        self.assertEqual(result, 20)

    def test_partial(self) -> None:
        """level == 0, power=40 → round(40 * 0.5 * 0.5) = 10."""
        outcome = CheckOutcomeFactory(success_level=0)
        result = outcome_to_delta(check_outcome=outcome, power=40, config=self.config)
        expected = round(40 * Decimal("0.5") * Decimal("0.5"))
        self.assertEqual(result, expected)
        self.assertEqual(result, 10)

    def test_failure(self) -> None:
        """level == -1, power=40 → round(40 * 0.0 * 0.5) = 0 (failure multiplier is 0.0)."""
        outcome = CheckOutcomeFactory(success_level=-1)
        result = outcome_to_delta(check_outcome=outcome, power=40, config=self.config)
        expected = round(40 * Decimal("0.0") * Decimal("0.5"))
        self.assertEqual(result, expected)
        self.assertEqual(result, 0)

    def test_botch(self) -> None:
        """level <= -2, power=40 → -round(40 * 0.5 * 0.5) = -10."""
        outcome = CheckOutcomeFactory(success_level=-2)
        result = outcome_to_delta(check_outcome=outcome, power=40, config=self.config)
        expected = -round(40 * Decimal("0.5") * Decimal("0.5"))
        self.assertEqual(result, expected)
        self.assertEqual(result, -10)

    def test_botch_is_negative(self) -> None:
        """Botch returns a negative delta (the committed power rebounds)."""
        outcome = CheckOutcomeFactory(success_level=-3)
        result = outcome_to_delta(check_outcome=outcome, power=20, config=self.config)
        self.assertLess(result, 0)

    def test_high_critical_clamps_to_critical_band(self) -> None:
        """success_level=10 is treated the same as level=3 (critical band)."""
        outcome_high = CheckOutcomeFactory(success_level=10)
        outcome_crit = CheckOutcomeFactory(success_level=3)
        power = 40
        self.assertEqual(
            outcome_to_delta(check_outcome=outcome_high, power=power, config=self.config),
            outcome_to_delta(check_outcome=outcome_crit, power=power, config=self.config),
        )

    def test_deep_botch_same_as_botch(self) -> None:
        """success_level=-10 is treated the same as level=-2 (botch band)."""
        outcome_deep = CheckOutcomeFactory(success_level=-10)
        outcome_botch = CheckOutcomeFactory(success_level=-2)
        power = 40
        self.assertEqual(
            outcome_to_delta(check_outcome=outcome_deep, power=power, config=self.config),
            outcome_to_delta(check_outcome=outcome_botch, power=power, config=self.config),
        )

    def test_zero_power_always_zero(self) -> None:
        """Any tier with power=0 returns 0 (no power, no progress)."""
        for level in (3, 2, 1, 0, -1):
            with self.subTest(level=level):
                outcome = CheckOutcomeFactory(success_level=level)
                self.assertEqual(
                    outcome_to_delta(check_outcome=outcome, power=0, config=self.config), 0
                )

    def test_botch_zero_power_returns_zero(self) -> None:
        """Botch with power=0 returns 0 (no power to backfire)."""
        outcome = CheckOutcomeFactory(success_level=-2)
        self.assertEqual(
            outcome_to_delta(check_outcome=outcome, power=0, config=self.config), 0
        )

    def test_return_type_is_int(self) -> None:
        """outcome_to_delta always returns a plain int, never Decimal."""
        outcome = CheckOutcomeFactory(success_level=2)
        result = outcome_to_delta(check_outcome=outcome, power=40, config=self.config)
        self.assertIsInstance(result, int)

    def test_botch_return_type_is_int(self) -> None:
        """Botch path also returns a plain int."""
        outcome = CheckOutcomeFactory(success_level=-2)
        result = outcome_to_delta(check_outcome=outcome, power=40, config=self.config)
        self.assertIsInstance(result, int)
