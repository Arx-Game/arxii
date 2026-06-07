"""Tests for cast_services: derive_cast_difficulty."""

from django.test import TestCase

from world.magic.factories import TechniqueFactory
from world.scenes.cast_services import derive_cast_difficulty


class TestDeriveCastDifficulty(TestCase):
    """derive_cast_difficulty maps technique intensity to the authored band scale (0-75)."""

    def test_low_intensity_lower_than_high_intensity(self) -> None:
        """A low-intensity technique must yield a lower difficulty than a high-intensity one."""
        low = TechniqueFactory(intensity=1, damage_profile=False)
        high = TechniqueFactory(intensity=9, damage_profile=False)
        assert derive_cast_difficulty(low) < derive_cast_difficulty(high)

    def test_result_in_expected_range(self) -> None:
        """The returned difficulty must be on the 0-100 scale (in practice a band value)."""
        for intensity in range(1, 10):
            technique = TechniqueFactory(intensity=intensity, damage_profile=False)
            difficulty = derive_cast_difficulty(technique)
            assert 0 <= difficulty <= 100, (
                f"difficulty={difficulty} out of range for intensity={intensity}"
            )

    def test_intensity_1_maps_to_band_15(self) -> None:
        """Intensity 1 should land in the first band (ceiling 2 → difficulty 15 = TRIVIAL)."""
        technique = TechniqueFactory(intensity=1, damage_profile=False)
        assert derive_cast_difficulty(technique) == 15

    def test_intensity_2_maps_to_band_15(self) -> None:
        """Intensity 2 is still ≤ ceiling 2, so difficulty is 15."""
        technique = TechniqueFactory(intensity=2, damage_profile=False)
        assert derive_cast_difficulty(technique) == 15

    def test_intensity_3_maps_to_band_30(self) -> None:
        """Intensity 3 is in the second band (ceiling 4 → difficulty 30 = EASY)."""
        technique = TechniqueFactory(intensity=3, damage_profile=False)
        assert derive_cast_difficulty(technique) == 30

    def test_intensity_5_maps_to_band_45(self) -> None:
        """Intensity 5 is in the third band (ceiling 6 → difficulty 45 = NORMAL)."""
        technique = TechniqueFactory(intensity=5, damage_profile=False)
        assert derive_cast_difficulty(technique) == 45

    def test_intensity_7_maps_to_band_60(self) -> None:
        """Intensity 7 is in the fourth band (ceiling 8 → difficulty 60 = HARD)."""
        technique = TechniqueFactory(intensity=7, damage_profile=False)
        assert derive_cast_difficulty(technique) == 60

    def test_intensity_9_maps_to_band_75(self) -> None:
        """Intensity 9 is in the final band (ceiling 9999 → difficulty 75 = DAUNTING)."""
        technique = TechniqueFactory(intensity=9, damage_profile=False)
        assert derive_cast_difficulty(technique) == 75

    def test_intensity_none_defaults_safely(self) -> None:
        """A technique with intensity=None (or 0) must not crash; treat as intensity 1."""
        technique = TechniqueFactory(intensity=1, damage_profile=False)
        # Force intensity to None to simulate a None value at runtime.
        technique.intensity = None
        assert derive_cast_difficulty(technique) == 15

    def test_intensity_zero_defaults_safely(self) -> None:
        """Intensity 0 must be treated as 1 (no negative/zero-difficulty exploits)."""
        technique = TechniqueFactory(intensity=1, damage_profile=False)
        technique.intensity = 0
        assert derive_cast_difficulty(technique) == 15
