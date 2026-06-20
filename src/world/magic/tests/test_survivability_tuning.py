from __future__ import annotations

from decimal import Decimal

from django.db import IntegrityError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import TargetKind, VitalBonusTarget
from world.magic.factories import (
    CharacterThreadWeavingUnlockFactory,
    ResonanceFactory,
    ThreadFactory,
    ThreadWeavingUnlockFactory,
)
from world.magic.models import ThreadSurvivabilityTuning
from world.magic.services import (
    get_thread_survivability_tuning,
    seed_thread_survivability_tuning,
    survivability_baseline,
    survivability_save_baselines,
    weave_thread,
)
from world.traits.factories import TraitFactory
from world.vitals.models import CharacterVitals


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
        self.assertEqual(ThreadSurvivabilityTuning.objects.count(), 5)
        dr = get_thread_survivability_tuning(VitalBonusTarget.DAMAGE_TAKEN_REDUCTION)
        self.assertEqual((dr.coefficient, dr.cap, dr.half_saturation), (1, 20, 8))
        hp = get_thread_survivability_tuning(VitalBonusTarget.MAX_HEALTH)
        self.assertEqual((hp.coefficient, hp.cap, hp.half_saturation), (1, 80, 10))
        for target in (
            VitalBonusTarget.DEATH_SAVE,
            VitalBonusTarget.KNOCKOUT_RESIST,
            VitalBonusTarget.PERMANENT_WOUND_RESIST,
        ):
            row = get_thread_survivability_tuning(target)
            self.assertEqual((row.coefficient, row.cap, row.half_saturation), (1, 15, 8))


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


# =============================================================================
# Recompute-on-change: weave_thread triggers max_health update (#1175)
# =============================================================================


class RecomputeOnThreadChangeTests(TestCase):
    def setUp(self) -> None:
        seed_thread_survivability_tuning()
        self.sheet = CharacterSheetFactory()
        CharacterVitals.objects.create(
            character_sheet=self.sheet,
            health=100,
            max_health=100,
            base_max_health=100,
        )

    def test_weaving_a_thread_updates_max_health(self) -> None:
        """Weaving a TRAIT thread triggers recompute_max_health_with_threads; max_health rises."""
        trait = TraitFactory()
        res = ResonanceFactory()
        # Mirrors WeaveThreadTests.test_weave_thread_trait_happy_path in test_resonance_services.py.
        unlock = ThreadWeavingUnlockFactory(target_kind=TargetKind.TRAIT, unlock_trait=trait)
        CharacterThreadWeavingUnlockFactory(character=self.sheet, unlock=unlock, xp_spent=100)

        weave_thread(self.sheet, TargetKind.TRAIT, trait, res, name="Survivability Test Thread")

        vitals = CharacterVitals.objects.get(character_sheet=self.sheet)
        # After weave S goes from 0 to 1 (level-0 thread counts as max(1,0//10)=1).
        # baseline = round(80 * 1 / (1 + 10)) ≈ 7 → max_health should exceed 100.
        self.assertGreater(vitals.max_health, 100)


# =============================================================================
# Save targets: DEATH_SAVE, KNOCKOUT_RESIST, PERMANENT_WOUND_RESIST (#1250)
# =============================================================================


class SaveTargetSeedTests(TestCase):
    def test_seed_creates_save_target_rows(self) -> None:
        seed_thread_survivability_tuning()
        for target in (
            VitalBonusTarget.DEATH_SAVE,
            VitalBonusTarget.KNOCKOUT_RESIST,
            VitalBonusTarget.PERMANENT_WOUND_RESIST,
        ):
            self.assertIsNotNone(get_thread_survivability_tuning(target))

    def test_save_baseline_zero_for_lone_wolf(self) -> None:
        seed_thread_survivability_tuning()
        lone = CharacterSheetFactory()  # no threads → lone wolf
        self.assertEqual(survivability_baseline(lone.character, VitalBonusTarget.DEATH_SAVE), 0)


class SurvivabilitySaveBaselinesTests(TestCase):
    """Tests for survivability_save_baselines() bundle (#1250)."""

    def setUp(self) -> None:
        seed_thread_survivability_tuning()
        self.sheet = CharacterSheetFactory()
        # Add a few threads so the invested character has a non-zero baseline.
        for _i in range(3):
            ThreadFactory(owner=self.sheet, resonance=ResonanceFactory(), level=10)

    def test_save_baselines_bundle_matches_per_target(self) -> None:
        char = self.sheet.character  # character WITH threads from setUp
        saves = survivability_save_baselines(char)
        self.assertEqual(saves.death, survivability_baseline(char, VitalBonusTarget.DEATH_SAVE))
        self.assertEqual(
            saves.knockout, survivability_baseline(char, VitalBonusTarget.KNOCKOUT_RESIST)
        )
        self.assertEqual(
            saves.wound,
            survivability_baseline(char, VitalBonusTarget.PERMANENT_WOUND_RESIST),
        )
        self.assertGreater(saves.death, 0)  # invested character benefits


# =============================================================================
# Coherence-amplifier tuning columns (#1252)
# =============================================================================


class CoherenceAmplifierDefaultsTests(TestCase):
    def test_tuning_has_amplifier_defaults(self) -> None:
        seed_thread_survivability_tuning()
        row = get_thread_survivability_tuning(VitalBonusTarget.DAMAGE_TAKEN_REDUCTION)
        self.assertEqual(row.coherence_scale, 50)
        self.assertEqual(row.coherence_max_multiplier, Decimal("2.00"))
