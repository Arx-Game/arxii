from django.test import TestCase

from world.combat.clash import outcome_to_delta
from world.combat.models import ClashConfig
from world.traits.factories import CheckOutcomeFactory


class OutcomeToDeltaTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.config, _ = ClashConfig.objects.get_or_create(pk=1)

    def test_critical_success(self) -> None:
        outcome = CheckOutcomeFactory(success_level=3)
        self.assertEqual(
            outcome_to_delta(check_outcome=outcome, config=self.config),
            self.config.delta_critical_success,
        )

    def test_great_success(self) -> None:
        outcome = CheckOutcomeFactory(success_level=2)
        self.assertEqual(
            outcome_to_delta(check_outcome=outcome, config=self.config),
            self.config.delta_great_success,
        )

    def test_success(self) -> None:
        outcome = CheckOutcomeFactory(success_level=1)
        self.assertEqual(
            outcome_to_delta(check_outcome=outcome, config=self.config),
            self.config.delta_success,
        )

    def test_partial(self) -> None:
        outcome = CheckOutcomeFactory(success_level=0)
        self.assertEqual(
            outcome_to_delta(check_outcome=outcome, config=self.config),
            self.config.delta_partial,
        )

    def test_failure(self) -> None:
        outcome = CheckOutcomeFactory(success_level=-1)
        self.assertEqual(
            outcome_to_delta(check_outcome=outcome, config=self.config),
            self.config.delta_failure,
        )

    def test_botch(self) -> None:
        outcome = CheckOutcomeFactory(success_level=-3)
        self.assertEqual(
            outcome_to_delta(check_outcome=outcome, config=self.config),
            self.config.delta_botch,
        )

    def test_high_critical_clamps_to_critical(self) -> None:
        outcome = CheckOutcomeFactory(success_level=10)
        self.assertEqual(
            outcome_to_delta(check_outcome=outcome, config=self.config),
            self.config.delta_critical_success,
        )

    def test_deep_botch_clamps_to_botch(self) -> None:
        outcome = CheckOutcomeFactory(success_level=-10)
        self.assertEqual(
            outcome_to_delta(check_outcome=outcome, config=self.config),
            self.config.delta_botch,
        )
