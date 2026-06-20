from __future__ import annotations

from django.db import IntegrityError
from django.test import TestCase

from world.magic.constants import VitalBonusTarget
from world.magic.models import ThreadSurvivabilityTuning
from world.magic.services import (
    get_thread_survivability_tuning,
    seed_thread_survivability_tuning,
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
