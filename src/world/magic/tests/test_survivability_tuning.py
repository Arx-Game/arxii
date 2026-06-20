from __future__ import annotations

from decimal import Decimal

from django.db import IntegrityError
from django.test import TestCase, tag

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


# =============================================================================
# Coherence amplifier: per-thread resonance wardrobe amplifies baseline (#1252)
# =============================================================================


@tag("postgres")
class CoherenceAmplifierBaselineTests(TestCase):
    """Verify that dressing coherently for a thread's resonance amplifies survivability_baseline.

    Tagged postgres: the equipped_items SharedMemoryModel handler uses the idmap cache,
    which is susceptible to SQLite pk-reset collisions across test boundaries — the same
    reason StyleFacetCoexistenceTests is postgres-tagged.

    Fixture design mirrors StyleFacetCoexistenceTests in test_aesthetic_composition.py:
    one Resonance, a Motif binding one Style to that Resonance, one item instance
    carrying that style equipped on the character. motif_coherence_bonus is exercised via
    the real walk (no mocks).
    """

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import CharacterFactory
        from world.items.constants import BodyRegion, EquipmentLayer
        from world.items.factories import (
            EquippedItemFactory,
            ItemInstanceFactory,
            ItemStyleFactory,
            ItemTemplateFactory,
            QualityTierFactory,
            StyleFactory,
            TemplateSlotFactory,
        )
        from world.magic.factories import (
            MotifFactory,
            MotifResonanceFactory,
            MotifResonanceStyleFactory,
        )

        seed_thread_survivability_tuning()

        cls.quality = QualityTierFactory(name="CoherenceAmpCommon", stat_multiplier="1.00")
        cls.resonance = ResonanceFactory()
        cls.style_bound = StyleFactory(name="CoherenceAmpBound")
        cls.style_unbound = StyleFactory(name="CoherenceAmpUnbound")

        # ---- invested character: sheet + thread on cls.resonance ----
        cls.char = CharacterFactory(db_key="CoherenceAmpChar")
        cls.sheet = CharacterSheetFactory(character=cls.char, primary_persona=False)
        ThreadFactory(owner=cls.sheet, resonance=cls.resonance, level=10)

        # Motif binding cls.style_bound to cls.resonance
        cls.motif = MotifFactory(character=cls.sheet)
        cls.mr = MotifResonanceFactory(motif=cls.motif, resonance=cls.resonance)
        MotifResonanceStyleFactory(motif_resonance=cls.mr, style=cls.style_bound)

        # Item carrying the bound style — equipped on cls.char
        template_a = ItemTemplateFactory(name="CoherenceAmpItemA")
        TemplateSlotFactory(
            template=template_a,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        cls.item_a = ItemInstanceFactory(template=template_a, quality_tier=cls.quality)
        ItemStyleFactory(
            item_instance=cls.item_a,
            style=cls.style_bound,
            attachment_quality_tier=cls.quality,
        )
        cls.equipped_a = EquippedItemFactory(
            character=cls.char,
            item_instance=cls.item_a,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )

        # Item carrying an UNBOUND style — for the uncoordinated test
        template_b = ItemTemplateFactory(name="CoherenceAmpItemB")
        TemplateSlotFactory(
            template=template_b,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.OUTER,
        )
        cls.item_b = ItemInstanceFactory(template=template_b, quality_tier=cls.quality)
        ItemStyleFactory(
            item_instance=cls.item_b,
            style=cls.style_unbound,
            attachment_quality_tier=cls.quality,
        )

        # ---- lone-wolf character: no threads, but dressed coherently ----
        cls.lone_char = CharacterFactory(db_key="CoherenceAmpLone")
        cls.lone_sheet = CharacterSheetFactory(character=cls.lone_char, primary_persona=False)
        lone_motif = MotifFactory(character=cls.lone_sheet)
        lone_mr = MotifResonanceFactory(motif=lone_motif, resonance=cls.resonance)
        MotifResonanceStyleFactory(motif_resonance=lone_mr, style=cls.style_bound)
        EquippedItemFactory(
            character=cls.lone_char,
            item_instance=cls.item_a,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )

    def _invalidate(self) -> None:
        self.char.equipped_items.invalidate()

    def _invalidate_lone(self) -> None:
        self.lone_char.equipped_items.invalidate()

    def test_coherence_amplifies_baseline(self) -> None:
        """A thread-invested character dressed in the bound style gets a HIGHER baseline."""
        from world.items.constants import BodyRegion, EquipmentLayer
        from world.items.factories import EquippedItemFactory

        # Baseline: unequip the bound-style item to simulate undressed state.
        self.equipped_a.delete()
        self._invalidate()
        try:
            plain = survivability_baseline(self.char, VitalBonusTarget.MAX_HEALTH)

            # Now re-equip the bound-style item.
            dressed = EquippedItemFactory(
                character=self.char,
                item_instance=self.item_a,
                body_region=BodyRegion.TORSO,
                equipment_layer=EquipmentLayer.BASE,
            )
            self._invalidate()
            try:
                amplified = survivability_baseline(self.char, VitalBonusTarget.MAX_HEALTH)
                self.assertGreater(
                    amplified,
                    plain,
                    f"Dressed baseline ({amplified}) must exceed undressed ({plain}).",
                )
            finally:
                dressed.delete()
                self._invalidate()
        finally:
            # Restore cls.equipped_a for other tests.
            from world.items.factories import EquippedItemFactory

            self.__class__.equipped_a = EquippedItemFactory(
                character=self.char,
                item_instance=self.item_a,
                body_region=BodyRegion.TORSO,
                equipment_layer=EquipmentLayer.BASE,
            )
            self._invalidate()

    def test_uncoordinated_wardrobe_is_inert(self) -> None:
        """Wearing only items with unbound styles leaves the baseline EQUAL to undressed.

        Dilution-only rule: motif_coherence_bonus returns 0 when no bound style is worn,
        so factor == 1.0 and the score is unchanged vs. the undressed character.
        """
        from world.items.constants import BodyRegion, EquipmentLayer
        from world.items.factories import EquippedItemFactory

        # Unequip the bound-style item first.
        self.equipped_a.delete()
        self._invalidate()
        try:
            plain = survivability_baseline(self.char, VitalBonusTarget.MAX_HEALTH)

            # Equip only the unbound-style item.
            uncoordinated = EquippedItemFactory(
                character=self.char,
                item_instance=self.item_b,
                body_region=BodyRegion.TORSO,
                equipment_layer=EquipmentLayer.OUTER,
            )
            self._invalidate()
            try:
                uncoordinated_result = survivability_baseline(
                    self.char, VitalBonusTarget.MAX_HEALTH
                )
                self.assertEqual(
                    uncoordinated_result,
                    plain,
                    "Wearing only unbound styles must not change the baseline "
                    f"(expected {plain}, got {uncoordinated_result}).",
                )
            finally:
                uncoordinated.delete()
                self._invalidate()
        finally:
            # Restore cls.equipped_a for other tests.
            from world.items.factories import EquippedItemFactory

            self.__class__.equipped_a = EquippedItemFactory(
                character=self.char,
                item_instance=self.item_a,
                body_region=BodyRegion.TORSO,
                equipment_layer=EquipmentLayer.BASE,
            )
            self._invalidate()

    def test_lone_wolf_zero_even_when_dressed(self) -> None:
        """A character with NO threads gets baseline 0 regardless of wardrobe."""
        self._invalidate_lone()
        result = survivability_baseline(self.lone_char, VitalBonusTarget.MAX_HEALTH)
        self.assertEqual(
            result,
            0,
            f"Lone wolf should have 0 baseline even when dressed, got {result}.",
        )
