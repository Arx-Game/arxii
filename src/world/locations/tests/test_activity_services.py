"""Activity band mapping from TRAFFIC (#745 — Spread a Tale Phase 1a, Task 4)."""

from django.test import SimpleTestCase

from world.locations.activity_services import band_for_traffic


class ActivityBandTest(SimpleTestCase):
    def test_empty_has_no_spread(self) -> None:
        band = band_for_traffic(0)
        self.assertEqual(band.label, "Empty")
        self.assertEqual(band.multiplier, 0.0)

    def test_busy_is_baseline(self) -> None:
        band = band_for_traffic(60)
        self.assertEqual(band.label, "Busy")
        self.assertEqual(band.multiplier, 1.0)

    def test_thronging_tops_out(self) -> None:
        band = band_for_traffic(100)
        self.assertEqual(band.label, "Thronging")
        self.assertGreater(band.multiplier, 1.0)

    def test_boundaries_pick_higher_band(self) -> None:
        self.assertEqual(band_for_traffic(70).label, "Bustling")
        self.assertEqual(band_for_traffic(69).label, "Busy")
