"""Tests for the qualitative anima band vocabulary (#1446 bundle 2).

Player-facing anima is narrative, not numerical (the magic app's key rule) — the band
is the word the status surfaces show instead of current/maximum.
"""

from django.test import TestCase

from world.magic.constants import ANIMA_BANDS, anima_band_for
from world.magic.factories import CharacterAnimaFactory
from world.magic.serializers import CharacterAnimaSerializer


class AnimaBandForTests(TestCase):
    def test_full_pool_is_top_band(self) -> None:
        self.assertEqual(anima_band_for(100, 100), ANIMA_BANDS[0][1])

    def test_half_pool_is_middle_band(self) -> None:
        self.assertEqual(anima_band_for(50, 100), "steady")

    def test_empty_pool_is_lowest_band(self) -> None:
        self.assertEqual(anima_band_for(0, 100), ANIMA_BANDS[-1][1])

    def test_zero_maximum_does_not_divide(self) -> None:
        self.assertEqual(anima_band_for(0, 0), ANIMA_BANDS[-1][1])

    def test_bands_descend_monotonically(self) -> None:
        thresholds = [threshold for threshold, _ in ANIMA_BANDS]
        self.assertEqual(thresholds, sorted(thresholds, reverse=True))
        self.assertEqual(ANIMA_BANDS[-1][0], 0.0)


class AnimaSerializerBandTests(TestCase):
    def test_band_serialized(self) -> None:
        anima = CharacterAnimaFactory(current=95, maximum=100)
        data = CharacterAnimaSerializer(instance=anima).data
        self.assertEqual(data["band"], ANIMA_BANDS[0][1])
