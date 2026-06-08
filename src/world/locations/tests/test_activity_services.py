"""Activity band mapping from TRAFFIC (#745 — Spread a Tale Phase 1a, Task 4)."""

from django.test import SimpleTestCase

from world.game_clock.constants import TimePhase
from world.locations.activity_services import band_for_traffic, room_activity_band


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


class RoomActivityBandPhaseTest(SimpleTestCase):
    """Time-of-day bends the band. room=None → traffic 50 (Busy baseline)."""

    def test_day_is_baseline(self) -> None:
        self.assertEqual(room_activity_band(None, ic_phase=TimePhase.DAY).label, "Busy")

    def test_night_quiets_the_room(self) -> None:
        # 50 × 0.5 = 25 → Quiet
        self.assertEqual(room_activity_band(None, ic_phase=TimePhase.NIGHT).label, "Quiet")

    def test_dawn_thins_the_room(self) -> None:
        # 50 × 0.6 = 30 → Steady
        self.assertEqual(room_activity_band(None, ic_phase=TimePhase.DAWN).label, "Steady")
