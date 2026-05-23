from django.test import TestCase

from world.combat.clash import strain_to_modifier
from world.combat.models import StrainConfig


class StrainConversionTests(TestCase):
    def setUp(self) -> None:
        self.config, _ = StrainConfig.objects.get_or_create(pk=1)

    def test_zero_strain_returns_zero(self) -> None:
        self.assertEqual(strain_to_modifier(anima_committed=0, config=self.config), 0)

    def test_modifier_rises_with_committed_anima(self) -> None:
        low = strain_to_modifier(anima_committed=1, config=self.config)
        mid = strain_to_modifier(anima_committed=10, config=self.config)
        high = strain_to_modifier(anima_committed=30, config=self.config)
        self.assertLess(low, mid)
        self.assertLess(mid, high)

    def test_diminishing_returns(self) -> None:
        # Marginal contribution of the 20th anima point is strictly less than
        # the marginal contribution of the 1st anima point.
        marginal_first = strain_to_modifier(
            anima_committed=1, config=self.config
        ) - strain_to_modifier(anima_committed=0, config=self.config)
        marginal_twentieth = strain_to_modifier(
            anima_committed=20, config=self.config
        ) - strain_to_modifier(anima_committed=19, config=self.config)
        self.assertLess(marginal_twentieth, marginal_first)

    def test_never_decreases(self) -> None:
        prev = -1
        for n in range(50):
            cur = strain_to_modifier(anima_committed=n, config=self.config)
            self.assertGreaterEqual(cur, prev)
            prev = cur
