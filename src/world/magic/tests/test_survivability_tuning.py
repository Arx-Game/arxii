from __future__ import annotations

from django.db import IntegrityError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import VitalBonusTarget
from world.magic.factories import ResonanceFactory, ThreadFactory
from world.magic.models import ThreadSurvivabilityTuning
from world.magic.services import (
    get_thread_survivability_tuning,
    seed_thread_survivability_tuning,
    survivability_baseline,
)


class ThreadSurvivabilityTuningModelTests(TestCase):
    def test_row_created_with_knobs(self) -> None:
        row = ThreadSurvivabilityTuning.objects.create(
            vital_target=VitalBonusTarget.DAMAGE_TAKEN_REDUCTION,
            coefficient=1,
            cap=20,
            half_saturation=8,
        )
        self.assertEqual(row.cap, 20)
        self.assertEqual(row.half_saturation, 8)

    def test_vital_target_is_unique(self) -> None:
        ThreadSurvivabilityTuning.objects.create(
            vital_target=VitalBonusTarget.MAX_HEALTH,
            cap=80,
            half_saturation=10,
        )
        with self.assertRaises(IntegrityError):
            ThreadSurvivabilityTuning.objects.create(
                vital_target=VitalBonusTarget.MAX_HEALTH,
                cap=99,
                half_saturation=99,
            )


class ThreadSurvivabilityTuningSeedTests(TestCase):
    def test_getter_returns_none_when_unseeded(self) -> None:
        self.assertIsNone(
            get_thread_survivability_tuning(VitalBonusTarget.DAMAGE_TAKEN_REDUCTION),
        )

    def test_seed_creates_dr_and_health_rows_idempotently(self) -> None:
        seed_thread_survivability_tuning()
        seed_thread_survivability_tuning()  # second call must be a no-op
        self.assertEqual(ThreadSurvivabilityTuning.objects.count(), 2)
        dr = get_thread_survivability_tuning(VitalBonusTarget.DAMAGE_TAKEN_REDUCTION)
        self.assertEqual((dr.coefficient, dr.cap, dr.half_saturation), (1, 20, 8))
        hp = get_thread_survivability_tuning(VitalBonusTarget.MAX_HEALTH)
        self.assertEqual((hp.coefficient, hp.cap, hp.half_saturation), (1, 80, 10))


class SurvivabilityBaselineTests(TestCase):
    def setUp(self) -> None:
        seed_thread_survivability_tuning()
        self.sheet = CharacterSheetFactory()

    def _add_threads(self, levels: list[int]) -> None:
        for lvl in levels:
            ThreadFactory(owner=self.sheet, resonance=ResonanceFactory(), level=lvl)

    def test_lone_wolf_is_zero(self) -> None:
        self.assertEqual(
            survivability_baseline(
                self.sheet.character,
                VitalBonusTarget.DAMAGE_TAKEN_REDUCTION,
            ),
            0,
        )

    def test_no_tuning_row_is_zero(self) -> None:
        ThreadSurvivabilityTuning.objects.all().delete()  # un-seed
        self._add_threads([10, 20, 30])
        self.assertEqual(
            survivability_baseline(
                self.sheet.character,
                VitalBonusTarget.DAMAGE_TAKEN_REDUCTION,
            ),
            0,
        )

    def test_dr_profiles_match_soft_cap(self) -> None:
        # S = Σ max(1, level//10). Three L10 threads → S=3. cap20 half8 → 60/11≈5.
        self._add_threads([10, 10, 10])
        self.assertEqual(
            survivability_baseline(
                self.sheet.character,
                VitalBonusTarget.DAMAGE_TAKEN_REDUCTION,
            ),
            5,
        )

    def test_health_profile_matches_soft_cap(self) -> None:
        # S=3 → cap80 half10 → 240/13≈18.
        self._add_threads([10, 10, 10])
        self.assertEqual(
            survivability_baseline(self.sheet.character, VitalBonusTarget.MAX_HEALTH),
            18,
        )

    def test_monotonic_more_investment_never_decreases(self) -> None:
        self._add_threads([10, 10, 10])
        low = survivability_baseline(
            self.sheet.character,
            VitalBonusTarget.DAMAGE_TAKEN_REDUCTION,
        )
        self.sheet.character.threads.invalidate()
        self._add_threads([30, 30, 30, 30])
        high = survivability_baseline(
            self.sheet.character,
            VitalBonusTarget.DAMAGE_TAKEN_REDUCTION,
        )
        self.assertGreater(high, low)
        self.assertLessEqual(high, 20)  # never exceeds cap
