from django.db.utils import IntegrityError
from django.test import TestCase

from world.societies.factories import LegendLevelCalibrationFactory
from world.societies.models import LegendLevelCalibration


class LegendLevelCalibrationTests(TestCase):
    def test_level_is_unique(self) -> None:
        LegendLevelCalibrationFactory(level=3)
        with self.assertRaises(IntegrityError):
            LegendLevelCalibrationFactory(level=3)

    def test_ordered_by_level(self) -> None:
        LegendLevelCalibrationFactory(level=5)
        LegendLevelCalibrationFactory(level=1)
        assert [r.level for r in LegendLevelCalibration.objects.all()] == [1, 5]

    def test_missing_row_raises_rather_than_defaulting(self) -> None:
        """Ruled behaviour: unauthored dials raise so the admin sentinel catches it."""
        with self.assertRaises(LegendLevelCalibration.DoesNotExist):
            LegendLevelCalibration.objects.get(level=99)

    def test_level_zero_is_authorable(self) -> None:
        """Station 0 means 'won outside a perilous contract'; staff decide if it can title."""
        row = LegendLevelCalibrationFactory(level=0, deed_title_threshold=0)
        assert LegendLevelCalibration.objects.get(level=0) == row
