"""Deterministic ordinary-cast strain contract tests (#3912)."""

from itertools import pairwise
from types import SimpleNamespace

from django.test import SimpleTestCase

from world.magic.services import strain_to_intensity
from world.magic.services.techniques import calculate_effective_anima_cost


class StrainContractTests(SimpleTestCase):
    """Pin conversion, cost, and non-lethal clamp semantics without balance data."""

    def setUp(self) -> None:
        self.config = SimpleNamespace(conversion_base=3, diminishing_step=2, diminishing_floor=1)

    def test_conversion_is_zero_monotonic_and_diminishing(self) -> None:
        values = [strain_to_intensity(strain_commitment=n, config=self.config) for n in range(8)]
        self.assertEqual(values[0], 0)
        self.assertTrue(all(a <= b for a, b in pairwise(values)))
        increments = [b - a for a, b in pairwise(values)]
        self.assertLess(increments[-1], increments[1])

    def test_no_moderate_and_dangerous_cost_examples(self) -> None:
        no_push = calculate_effective_anima_cost(
            base_cost=2, runtime_intensity=0, runtime_control=0, current_anima=10
        )
        moderate = calculate_effective_anima_cost(
            base_cost=2,
            runtime_intensity=0,
            runtime_control=0,
            current_anima=10,
            strain_commitment=3,
        )
        dangerous = calculate_effective_anima_cost(
            base_cost=2,
            runtime_intensity=0,
            runtime_control=0,
            current_anima=3,
            strain_commitment=3,
        )
        self.assertEqual((no_push.effective_cost, no_push.deficit), (2, 0))
        self.assertEqual((moderate.effective_cost, moderate.deficit), (5, 0))
        self.assertEqual((dangerous.effective_cost, dangerous.deficit), (5, 2))
        self.assertGreater(strain_to_intensity(strain_commitment=3, config=self.config), 0)

    def test_non_lethal_cost_clamp_has_no_deficit(self) -> None:
        result = calculate_effective_anima_cost(
            base_cost=2,
            runtime_intensity=0,
            runtime_control=0,
            current_anima=3,
            strain_commitment=5,
            lethal=False,
        )
        self.assertEqual(result.effective_cost, 3)
        self.assertEqual(result.deficit, 0)
