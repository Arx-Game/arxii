from django.test import TestCase

from world.combat.clash import strain_to_intensity
from world.combat.models import StrainConfig


class StrainIntensityConversionTests(TestCase):
    def setUp(self) -> None:
        self.config, _ = StrainConfig.objects.get_or_create(pk=1)

    def test_zero_strain_returns_zero(self) -> None:
        self.assertEqual(strain_to_intensity(strain_commitment=0, config=self.config), 0)

    def test_intensity_rises_with_committed_anima(self) -> None:
        low = strain_to_intensity(strain_commitment=1, config=self.config)
        mid = strain_to_intensity(strain_commitment=10, config=self.config)
        high = strain_to_intensity(strain_commitment=30, config=self.config)
        self.assertLess(low, mid)
        self.assertLess(mid, high)

    def test_diminishing_returns(self) -> None:
        # Marginal contribution of the 20th anima point is strictly less than
        # the marginal contribution of the 1st anima point.
        marginal_first = strain_to_intensity(
            strain_commitment=1, config=self.config
        ) - strain_to_intensity(strain_commitment=0, config=self.config)
        marginal_twentieth = strain_to_intensity(
            strain_commitment=20, config=self.config
        ) - strain_to_intensity(strain_commitment=19, config=self.config)
        self.assertLess(marginal_twentieth, marginal_first)

    def test_never_decreases(self) -> None:
        prev = -1
        for n in range(50):
            cur = strain_to_intensity(strain_commitment=n, config=self.config)
            self.assertGreaterEqual(cur, prev)
            prev = cur

    def test_strain_to_intensity_monotonic_diminishing(self) -> None:
        cfg, _ = StrainConfig.objects.get_or_create(pk=1)
        self.assertEqual(strain_to_intensity(strain_commitment=0, config=cfg), 0)
        a = strain_to_intensity(strain_commitment=5, config=cfg)
        b = strain_to_intensity(strain_commitment=10, config=cfg)
        self.assertGreater(a, 0)
        self.assertGreater(b, a)
        self.assertLess(b - a, a)  # diminishing returns: second block adds less than first
