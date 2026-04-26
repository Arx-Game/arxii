"""End-to-end pipeline tests for the per-cast corruption accrual hook (PR #403).

User story:
    As a character, casting a non-Celestial technique causes my corruption to
    rise in proportion to the resonance involved, the technique tier, and
    whether I am in heightened states such as Audere, anima deficit, or
    suffering a control mishap.

Covers gaps NOT already exercised by FullCastPipelineCorruptionTests
(world/magic/tests/integration/test_corruption_flow.py):

    1. Audere push multiplier — Abyssal cast while character is in Audere
       accrues more corruption than the same cast without Audere (×1.5).
    2. Multi-resonance split attribution — a Gift with 2 Abyssal resonances
       splits runtime intensity equally; each resonance accrues its share.
    3. Stacked multipliers (deficit + Audere) — both flags true; asserts
       the combined × 3.0 multiplier is applied (per spec §3.1 formula).
    4. CORRUPTION_ACCRUING / CORRUPTION_ACCRUED events fire from the
       cast-driven path (not a direct accrue_corruption call).

All tests drive the full use_technique() orchestrator (Step 9 fires
accrue_corruption_for_cast). Direct calls to accrue_corruption_for_cast
are unit-test territory; these tests prove the pipeline wiring.

CorruptionConfig defaults (integer-tenths, all × 0.1):
    abyssal_coefficient  = 10  (× 1.0 per involvement unit)
    tier_1_coefficient   = 10  (× 1.0 for level 1–5 techniques)
    audere_multiplier    = 15  (× 1.5 on top of 10-neutral)
    deficit_multiplier   = 20  (× 2.0)
    mishap_multiplier    = 15  (× 1.5)

Tick formula (spec §3.1):
    base_tick   = involvement × (affinity_coef / 10) × (tier_coef / 10)
    multipliers = (d × m × a) / 1000   (each of d/m/a is the configured
                  integer-tenths value when flag=True, else 10/neutral)
    tick        = ceil(base_tick × multipliers)
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase


class TestCorruptionPerCastPipeline(TestCase):
    """Per-cast corruption hook pipeline — Audere, multi-resonance, stacked multipliers.

    setUpTestData calls seed_magic_config() to set up all required singletons
    (AnimaConfig, SoulfrayConfig, ResonanceGainConfig, CorruptionConfig, etc.)
    with correct types.  seed_magic_config() now stores SoulfrayConfig's
    soulfray_threshold_ratio as Decimal("0.30"), so use_technique()'s Step 7
    soulfray guard no longer raises TypeError.

    Individual tests create their own characters, CharacterAnima rows, and
    resonances with ConditionTemplates so each scenario is fully isolated.
    The simple _make_simple_corruption_template() helper is used rather than
    CorruptionConditionTemplateFactory to keep thresholds deterministic and
    avoid the HOLD_OVERFLOW resist check that can gate stage advancement.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        from integration_tests.game_content.magic import seed_magic_config

        # seed_magic_config() creates all required singletons (including
        # SoulfrayConfig with Decimal("0.30") for soulfray_threshold_ratio)
        # and the CorruptionConfig with default coefficients.
        result = seed_magic_config()
        cls.corruption_config = result.corruption_config

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _make_simple_corruption_template(resonance: object) -> object:
        """Create a simple 5-stage Corruption ConditionTemplate for resonance.

        Uses ADVANCE_AT_THRESHOLD (no HOLD_OVERFLOW resist check) so stage
        advancement is deterministic in tests.  Thresholds: 50, 200, 500,
        1000, 1500.

        Idempotent: if stages already exist on the template (--keepdb reuse),
        stage creation is skipped.
        """
        from world.conditions.factories import (
            ConditionStageFactory,
            ConditionTemplateFactory,
        )

        template = ConditionTemplateFactory(
            name=f"Corruption ({resonance.name} pipeline test)",
            has_progression=True,
            corruption_resonance=resonance,
        )
        # Guard: skip stage creation if stages already exist (--keepdb idempotency).
        if template.stages.exists():
            return template
        thresholds = [50, 200, 500, 1000, 1500]
        for i, threshold in enumerate(thresholds, start=1):
            ConditionStageFactory(
                condition=template,
                stage_order=i,
                severity_threshold=threshold,
            )
        return template

    @staticmethod
    def _make_abyssal_gift_technique(
        *,
        intensity: int = 5,
        control: int = 10,
        anima_cost: int = 2,
        level: int = 1,
        resonance_count: int = 1,
    ) -> tuple:
        """Create Abyssal resonance(s) + Gift + Technique.

        Returns (resonances_list, gift, technique).

        When resonance_count > 1 all resonances share the same Abyssal
        affinity and are added to the same Gift, so the involvement split
        spreads evenly across all of them.
        """
        from world.magic.factories import (
            AffinityFactory,
            GiftFactory,
            ResonanceFactory,
            TechniqueFactory,
        )

        abyssal_affinity = AffinityFactory(name="Abyssal")
        resonances = [
            ResonanceFactory(name=f"Test Abyssal Res {i}", affinity=abyssal_affinity)
            for i in range(resonance_count)
        ]
        gift = GiftFactory()
        for res in resonances:
            gift.resonances.add(res)
        technique = TechniqueFactory(
            gift=gift,
            intensity=intensity,
            control=control,
            anima_cost=anima_cost,
            level=level,
        )
        return resonances, gift, technique

    # -----------------------------------------------------------------------
    # Scenario 1: Audere push multiplier
    # -----------------------------------------------------------------------

    def test_audere_multiplier_amplifies_corruption(self) -> None:
        """Abyssal cast with character in Audere accrues more than without.

        Setup:
            intensity=5, control=10 (+ social safety +10 = runtime_control=20),
            level=1 (tier 1).  1 Abyssal resonance.
            involvement = runtime_intensity // 1 = 5
            base_tick = 5 × (10/10) × (10/10) = 5

        Without Audere (multipliers = 10×10×10/1000 = 1.0):
            tick = ceil(5 × 1.0) = 5

        With Audere (multipliers = 10×10×15/1000 = 1.5):
            tick = ceil(5 × 1.5) = ceil(7.5) = 8

        The test creates two characters — one baseline, one with an Audere
        ConditionInstance — and asserts the Audere character accrues more.
        """
        from world.character_sheets.factories import CharacterSheetFactory
        from world.conditions.factories import (
            ConditionInstanceFactory,
            ConditionTemplateFactory,
        )
        from world.magic.factories import CharacterAnimaFactory
        from world.magic.models.aura import CharacterResonance
        from world.magic.services import use_technique

        resonances_base, _gift_base, technique_base = self._make_abyssal_gift_technique(
            intensity=5, control=10, anima_cost=2, level=1
        )
        resonances_audere, _gift_audere, technique_audere = self._make_abyssal_gift_technique(
            intensity=5, control=10, anima_cost=2, level=1
        )
        res_base = resonances_base[0]
        res_audere = resonances_audere[0]

        self._make_simple_corruption_template(res_base)
        self._make_simple_corruption_template(res_audere)

        sheet_base = CharacterSheetFactory()
        CharacterAnimaFactory(character=sheet_base.character, current=20, maximum=20)

        sheet_audere = CharacterSheetFactory()
        CharacterAnimaFactory(character=sheet_audere.character, current=20, maximum=20)

        # Put sheet_audere's character in Audere by creating the ConditionInstance directly.
        # _character_is_in_audere() checks for ConditionInstance where
        # condition.name = "Audere".  We can create that directly with a factory
        # without going through the full gate check (which requires engagement + Soulfray).
        audere_template = ConditionTemplateFactory(name="Audere")
        ConditionInstanceFactory(
            target=sheet_audere.character,
            condition=audere_template,
        )

        # Baseline cast (no Audere)
        result_base = use_technique(
            character=sheet_base.character,
            technique=technique_base,
            resolve_fn=lambda: None,
        )

        # Audere cast
        result_audere = use_technique(
            character=sheet_audere.character,
            technique=technique_audere,
            resolve_fn=lambda: None,
        )

        # Both should have accrual results
        self.assertIsNotNone(result_base.corruption_summary)
        self.assertIsNotNone(result_audere.corruption_summary)

        # was_audere flag should differ
        self.assertFalse(result_base.was_audere)
        self.assertTrue(result_audere.was_audere)

        # Assert Audere character accrues more corruption
        char_res_base = CharacterResonance.objects.get(
            character_sheet=sheet_base, resonance=res_base
        )
        char_res_audere = CharacterResonance.objects.get(
            character_sheet=sheet_audere, resonance=res_audere
        )

        # Without Audere: tick = ceil(5 × 1.0) = 5
        self.assertEqual(char_res_base.corruption_current, 5)
        # With Audere: tick = ceil(5 × 1.5) = ceil(7.5) = 8
        self.assertEqual(char_res_audere.corruption_current, 8)
        # Audere character should always have strictly more
        self.assertGreater(
            char_res_audere.corruption_current,
            char_res_base.corruption_current,
        )

    # -----------------------------------------------------------------------
    # Scenario 2: Multi-resonance split attribution
    # -----------------------------------------------------------------------

    def test_multi_resonance_split_attribution(self) -> None:
        """Gift with 2 Abyssal resonances splits involvement equally between them.

        Setup:
            intensity=10, level=1 (tier 1).  2 Abyssal resonances on the Gift.
            per_resonance_share = 10 // 2 = 5 (integer division per spec §10.1)
            base_tick per resonance = 5 × (10/10) × (10/10) = 5
            multipliers = 10×10×10/1000 = 1.0 (no flags set)
            tick per resonance = ceil(5 × 1.0) = 5

        Both resonances should increment corruption_current and
        corruption_lifetime by 5.  Accrual summary has 2 per_resonance entries.
        """
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import CharacterAnimaFactory
        from world.magic.models.aura import CharacterResonance
        from world.magic.services import use_technique

        resonances, _gift, technique = self._make_abyssal_gift_technique(
            intensity=10, control=10, anima_cost=2, level=1, resonance_count=2
        )
        res_a, res_b = resonances

        self._make_simple_corruption_template(res_a)
        self._make_simple_corruption_template(res_b)

        sheet = CharacterSheetFactory()
        CharacterAnimaFactory(character=sheet.character, current=20, maximum=20)

        result = use_technique(
            character=sheet.character,
            technique=technique,
            resolve_fn=lambda: None,
        )

        self.assertIsNotNone(result.corruption_summary)
        # Both resonances should appear in per_resonance accrual list
        self.assertEqual(len(result.corruption_summary.per_resonance), 2)

        char_res_a = CharacterResonance.objects.get(character_sheet=sheet, resonance=res_a)
        char_res_b = CharacterResonance.objects.get(character_sheet=sheet, resonance=res_b)

        # Equal split: each resonance should receive involvement=5 → tick=5
        self.assertEqual(char_res_a.corruption_current, 5)
        self.assertEqual(char_res_a.corruption_lifetime, 5)
        self.assertEqual(char_res_b.corruption_current, 5)
        self.assertEqual(char_res_b.corruption_lifetime, 5)

    # -----------------------------------------------------------------------
    # Scenario 3: Stacked multipliers — deficit + Audere
    # -----------------------------------------------------------------------

    def test_stacked_deficit_and_audere_multipliers(self) -> None:
        """Cast with deficit + Audere both active stacks multipliers per spec §3.1.

        Setup:
            intensity=5, control=10, anima_cost=30, current_anima=2,
            level=1 (tier 1), 1 Abyssal resonance.

            Social safety bonus applies (+10 control, no engagement):
              runtime_control = 10 + 10 = 20
              control_delta   = 20 - 5  = 15
              effective_cost  = max(30 - 15, 0) = 15
              deficit         = max(15 - 2, 0) = 13  → was_deficit=True

            Audere ConditionInstance created → was_audere=True.

            involvement = 5 (runtime_intensity // 1)
            base_tick = 5 × (10/10) × (10/10) = 5
            multipliers = (20 × 10 × 15) / 1000 = 3.0
            tick = ceil(5 × 3.0) = 15

        Compared to neutral tick (no flags) = 5 (3× uplift).
        """
        from world.character_sheets.factories import CharacterSheetFactory
        from world.conditions.factories import (
            ConditionInstanceFactory,
            ConditionTemplateFactory,
        )
        from world.magic.factories import CharacterAnimaFactory
        from world.magic.models.aura import CharacterResonance
        from world.magic.services import use_technique

        resonances, _gift, technique = self._make_abyssal_gift_technique(
            intensity=5,
            control=10,
            anima_cost=30,  # high cost to force deficit
            level=1,
        )
        res = resonances[0]
        self._make_simple_corruption_template(res)

        sheet = CharacterSheetFactory()
        # Low current anima ensures deficit: effective_cost=15 > current=2
        CharacterAnimaFactory(character=sheet.character, current=2, maximum=50)

        # Apply Audere ConditionInstance.
        # _character_is_in_audere() checks condition__name == AUDERE_CONDITION_NAME = "Audere".
        # Use get_or_create via the factory so the template already created by Scenario 1
        # (--keepdb) is reused safely.
        from world.magic.audere import AUDERE_CONDITION_NAME

        audere_template = ConditionTemplateFactory(name=AUDERE_CONDITION_NAME)
        ConditionInstanceFactory(
            target=sheet.character,
            condition=audere_template,
        )

        result = use_technique(
            character=sheet.character,
            technique=technique,
            resolve_fn=lambda: None,
        )

        self.assertIsNotNone(result.corruption_summary)
        self.assertTrue(result.was_deficit, "Expected was_deficit=True with anima=2, cost=15")
        self.assertTrue(result.was_audere, "Expected was_audere=True with Audere condition active")

        char_res = CharacterResonance.objects.get(character_sheet=sheet, resonance=res)
        # stacked tick = ceil(5 × 3.0) = 15
        self.assertEqual(char_res.corruption_current, 15)
        self.assertEqual(char_res.corruption_lifetime, 15)

    # -----------------------------------------------------------------------
    # Scenario 4: CORRUPTION_ACCRUING + CORRUPTION_ACCRUED events fire from cast path
    # -----------------------------------------------------------------------

    def test_cast_emits_corruption_accruing_and_accrued_events(self) -> None:
        """The cast-driven pipeline fires CORRUPTION_ACCRUING and CORRUPTION_ACCRUED.

        Verifies that the reactive event layer fires for each per-resonance
        accrual step when routed through use_technique → accrue_corruption_for_cast
        → accrue_corruption.  The character must have a location so emit_event
        fires (it is suppressed when location is None).

        Uses a single Abyssal resonance with intensity=5, level=1.
        Expected: 1 CORRUPTION_ACCRUING + 1 CORRUPTION_ACCRUED emitted.
        """
        from evennia.objects.models import ObjectDB

        from flows.constants import EventName
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import CharacterAnimaFactory
        from world.magic.services import use_technique

        resonances, _gift, technique = self._make_abyssal_gift_technique(
            intensity=5, control=10, anima_cost=2, level=1
        )
        res = resonances[0]
        self._make_simple_corruption_template(res)

        sheet = CharacterSheetFactory()
        CharacterAnimaFactory(character=sheet.character, current=20, maximum=20)

        # Give the character a location so emit_event fires (skipped when location is None).
        room = ObjectDB.objects.create(
            db_key="CorruptionPipelineTestRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        sheet.character.location = room

        emitted_event_names: list[str] = []
        import world.magic.services.corruption as corruption_mod

        original_emit = corruption_mod.emit_event

        def capturing_emit(
            event_name: str, payload: object, location: object, **kwargs: object
        ) -> object:
            emitted_event_names.append(event_name)
            return original_emit(event_name, payload, location, **kwargs)

        with patch("world.magic.services.corruption.emit_event", side_effect=capturing_emit):
            use_technique(
                character=sheet.character,
                technique=technique,
                resolve_fn=lambda: None,
            )

        self.assertIn(
            EventName.CORRUPTION_ACCRUING,
            emitted_event_names,
            "Expected CORRUPTION_ACCRUING to fire from cast-driven path",
        )
        self.assertIn(
            EventName.CORRUPTION_ACCRUED,
            emitted_event_names,
            "Expected CORRUPTION_ACCRUED to fire from cast-driven path",
        )
