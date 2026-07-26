from decimal import Decimal

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassLevelFactory
from world.conditions.factories import (
    CapabilityTypeFactory,
    ConditionCapabilityEffectFactory,
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.conditions.models import CapabilityType
from world.conditions.services import (
    apply_condition,
    get_all_capability_values,
    get_capability_status,
    get_effective_capability_value,
)
from world.conditions.views import _aggregate_capability_effects, _build_effect_lookups
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
)
from world.magic.constants import EffectKind, TargetKind
from world.magic.factories import (
    CharacterTechniqueFactory,
    GiftFactory,
    ResonanceFactory,
    TechniqueCapabilityGrantFactory,
    TechniqueFactory,
    ThreadFactory,
    ThreadPullEffectFactory,
)
from world.magic.models import CapabilityPowerConfig, LevelPowerConfig, Thread
from world.magic.types.pull import PullActionContext
from world.mechanics.factories import ModifierCategoryFactory, PrerequisiteFactory
from world.mechanics.models import CharacterModifier, ModifierSource, ModifierTarget


class CapabilityInnateBaselineTests(TestCase):
    def test_innate_baseline_defaults_zero(self) -> None:
        cap = CapabilityTypeFactory(name="force")
        self.assertEqual(cap.innate_baseline, 0)

    def test_innate_baseline_settable(self) -> None:
        cap = CapabilityTypeFactory(name="awareness", innate_baseline=1)
        self.assertEqual(cap.innate_baseline, 1)


class GetEffectiveCapabilityValueTests(TestCase):
    """Tests for get_effective_capability_value: baseline + modifiers + conditions."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character

    def _make_character_modifier(self, capability: CapabilityType, value: int) -> CharacterModifier:
        """Create a CharacterModifier targeting the given capability on self.sheet."""
        category = ModifierCategoryFactory(name="capability")
        target = ModifierTarget.objects.create(
            name=f"capability_{capability.pk}",
            category=category,
            description="test",
            display_order=0,
            is_active=True,
            target_capability=capability,
        )
        source = ModifierSource.objects.create()
        return CharacterModifier.objects.create(
            character=self.sheet,
            target=target,
            value=value,
            source=source,
        )

    def test_baseline_only_no_conditions_no_modifiers(self) -> None:
        """Awareness innate_baseline=1, no conditions/modifiers → effective 1."""
        cap = CapabilityTypeFactory(name="awareness_eff", innate_baseline=1)
        result = get_effective_capability_value(self.character.sheet_data, cap)
        self.assertEqual(result, 1)

    def test_condition_impairment_floors_at_zero(self) -> None:
        """Unconscious applies awareness −100 → effective value floors at 0."""
        cap = CapabilityTypeFactory(name="awareness_imp", innate_baseline=1)
        condition = ConditionTemplateFactory(name="unconscious_test")
        ConditionCapabilityEffectFactory(condition=condition, capability=cap, value=-100)
        apply_condition(target=self.character, condition=condition)

        result = get_effective_capability_value(self.character.sheet_data, cap)
        self.assertEqual(result, 0)

    def test_character_modifier_enhances(self) -> None:
        """CharacterModifier +3 on movement (baseline 1) → effective 4."""
        cap = CapabilityTypeFactory(name="movement_enh", innate_baseline=1)
        self._make_character_modifier(cap, value=3)

        result = get_effective_capability_value(self.character.sheet_data, cap)
        self.assertEqual(result, 4)

    def test_negative_modifier_reduces_to_floor(self) -> None:
        """CharacterModifier −1 on movement (baseline 1) → effective 0."""
        cap = CapabilityTypeFactory(name="movement_neg", innate_baseline=1)
        self._make_character_modifier(cap, value=-1)

        result = get_effective_capability_value(self.character.sheet_data, cap)
        self.assertEqual(result, 0)


class TechniqueCapabilityGrantFoldingTests(TestCase):
    """#2504: technique-granted capabilities feed the agency oracle.

    Only prerequisite-null grants count; when several known techniques grant
    the same capability, the fold is MAX not sum (ADR-0034 individuation) so
    stacking many techniques never inflates an unrelated capability.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()

    def test_known_technique_prereq_null_grant_raises_effective_value(self) -> None:
        """(a) A known technique's prerequisite-null grant adds calculate_value()."""
        cap = CapabilityTypeFactory(name="technique_grant_a", innate_baseline=0)
        technique = TechniqueFactory(intensity=2)
        grant = TechniqueCapabilityGrantFactory(
            technique=technique,
            capability=cap,
            base_value=5,
            intensity_multiplier=1,
        )
        CharacterTechniqueFactory(character=self.sheet, technique=technique)

        result = get_effective_capability_value(self.sheet, cap)
        self.assertEqual(result, grant.calculate_value())
        self.assertEqual(result, 7)

    def test_two_techniques_same_capability_use_max_not_sum(self) -> None:
        """(b) Two known techniques granting the same capability → max, not sum."""
        cap = CapabilityTypeFactory(name="technique_grant_b", innate_baseline=0)
        low_technique = TechniqueFactory(intensity=1)
        high_technique = TechniqueFactory(intensity=1)
        low_grant = TechniqueCapabilityGrantFactory(
            technique=low_technique, capability=cap, base_value=2, intensity_multiplier=0
        )
        high_grant = TechniqueCapabilityGrantFactory(
            technique=high_technique, capability=cap, base_value=9, intensity_multiplier=0
        )
        CharacterTechniqueFactory(character=self.sheet, technique=low_technique)
        CharacterTechniqueFactory(character=self.sheet, technique=high_technique)

        result = get_effective_capability_value(self.sheet, cap)
        self.assertEqual(result, max(low_grant.calculate_value(), high_grant.calculate_value()))
        self.assertEqual(result, 9)

    def test_grant_with_prerequisite_is_ignored(self) -> None:
        """(c) A grant carrying a source-level prerequisite is availability-only."""
        cap = CapabilityTypeFactory(name="technique_grant_c", innate_baseline=0)
        technique = TechniqueFactory(intensity=5)
        TechniqueCapabilityGrantFactory(
            technique=technique,
            capability=cap,
            base_value=10,
            intensity_multiplier=1,
            prerequisite=PrerequisiteFactory(),
        )
        CharacterTechniqueFactory(character=self.sheet, technique=technique)

        result = get_effective_capability_value(self.sheet, cap)
        self.assertEqual(result, 0)

    def test_unknown_technique_grant_is_ignored(self) -> None:
        """(d) A technique the character does not know contributes nothing."""
        cap = CapabilityTypeFactory(name="technique_grant_d", innate_baseline=0)
        technique = TechniqueFactory(intensity=5)
        TechniqueCapabilityGrantFactory(
            technique=technique, capability=cap, base_value=10, intensity_multiplier=1
        )
        # No CharacterTechniqueFactory linking this technique to self.sheet.

        result = get_effective_capability_value(self.sheet, cap)
        self.assertEqual(result, 0)

    def test_non_positive_calculated_value_is_ignored(self) -> None:
        """(e) calculate_value() <= 0 does not contribute (and cannot go negative)."""
        cap = CapabilityTypeFactory(name="technique_grant_e", innate_baseline=0)
        technique = TechniqueFactory(intensity=0)
        TechniqueCapabilityGrantFactory(
            technique=technique, capability=cap, base_value=0, intensity_multiplier=0
        )
        CharacterTechniqueFactory(character=self.sheet, technique=technique)

        result = get_effective_capability_value(self.sheet, cap)
        self.assertEqual(result, 0)

    def test_conditions_still_stack_additively_on_top(self) -> None:
        """(g) Existing condition-additive behavior is unchanged alongside the technique term."""
        cap = CapabilityTypeFactory(name="technique_grant_g", innate_baseline=0)
        technique = TechniqueFactory(intensity=1)
        grant = TechniqueCapabilityGrantFactory(
            technique=technique, capability=cap, base_value=5, intensity_multiplier=0
        )
        CharacterTechniqueFactory(character=self.sheet, technique=technique)

        condition = ConditionTemplateFactory(name="technique_grant_g_condition")
        ConditionCapabilityEffectFactory(condition=condition, capability=cap, value=2)
        apply_condition(target=self.sheet.character, condition=condition)

        result = get_effective_capability_value(self.sheet, cap)
        self.assertEqual(result, grant.calculate_value() + 2)
        self.assertEqual(result, 7)


class ThreadCapabilityGrantValueTests(TestCase):
    """CharacterThreadHandler.passive_capability_grants magnitude curve (#2708).

    A tier-0 CAPABILITY_GRANT ThreadPullEffect used to contribute a hardcoded +1
    regardless of thread level or power. It now curves via
    ``apply_capability_curve``, scaled by ``thread_level_multiplier(thread.level)``
    and the character's ``context_free_power`` — EXCEPT the #2022
    ``CovenantRole.granted_capabilities`` M2M source, which has no thread, no
    level, and no ``capability_grant_value``, and must stay flat at 1.
    """

    def _trait_capability_grant(
        self,
        *,
        sheet,
        level: int,
        capability: CapabilityType,
        capability_grant_value: int = 1,
        min_thread_level: int = 0,
    ) -> None:
        """Author a TRAIT-kind thread + its tier-0 CAPABILITY_GRANT effect row.

        TRAIT-kind threads need no engagement gate (unlike COVENANT_ROLE), which
        keeps these tests focused on the magnitude curve rather than engagement.
        """
        resonance = ResonanceFactory()
        ThreadFactory(owner=sheet, resonance=resonance, level=level)
        ThreadPullEffectFactory(
            target_kind=TargetKind.TRAIT,
            resonance=resonance,
            tier=0,
            min_thread_level=min_thread_level,
            effect_kind=EffectKind.CAPABILITY_GRANT,
            flat_bonus_amount=None,
            capability_grant=capability,
            capability_grant_value=capability_grant_value,
        )

    def test_inert_without_config_still_grants_one(self) -> None:
        """Pre-#2708 behaviour: a tier-0 CAPABILITY_GRANT contributes exactly +1."""
        sheet = CharacterSheetFactory()
        cap = CapabilityTypeFactory()
        self._trait_capability_grant(sheet=sheet, level=10, capability=cap)

        # No CapabilityPowerConfig row anywhere in this test -> curve disabled.
        granted = sheet.character.threads.passive_capability_grants()
        self.assertEqual(granted[cap.pk], 1)

    def test_level_10_thread_beats_level_1_thread(self) -> None:
        """The defect this fixes: today these are identical."""
        CapabilityPowerConfig.objects.create(pk=1, power_per_doubling=10)
        LevelPowerConfig.objects.create(pk=1, character_level_bonus=10, technique_level_bonus=0)

        low_sheet = CharacterSheetFactory()
        CharacterClassLevelFactory(character=low_sheet, level=1)
        cap_low = CapabilityTypeFactory()
        self._trait_capability_grant(sheet=low_sheet, level=1, capability=cap_low)

        high_sheet = CharacterSheetFactory()
        CharacterClassLevelFactory(character=high_sheet, level=1)
        cap_high = CapabilityTypeFactory()
        self._trait_capability_grant(sheet=high_sheet, level=10, capability=cap_high)

        low_value = low_sheet.character.threads.passive_capability_grants()[cap_low.pk]
        high_value = high_sheet.character.threads.passive_capability_grants()[cap_high.pk]
        self.assertGreater(high_value, low_value)

    def test_availability_oracle_matches_agency_oracle_for_same_grant(self) -> None:
        """#2708 Task 6 regression: the availability oracle must fold the SAME
        curved value the agency oracle reads for one thread-passive grant.

        ``get_all_capability_values`` (availability oracle: feeds
        ``mechanics._get_condition_sources`` -> ``CapabilitySource.value`` ->
        ``resolve_challenge``'s dice roll) used to add a hardcoded +1 per granted
        capability, discarding the curved magnitude that
        ``_passive_capability_grants`` returns. ``get_effective_capability_value``
        (agency oracle) already read the real curved value via its
        ``grant_floor`` term. A level-10 thread and a level-1 thread would
        therefore reach the roll identically even though the agency oracle told
        them apart. Asserting the two oracles equal each other (not a hardcoded
        number) keeps this guard valid if the curve is retuned later.
        """
        CapabilityPowerConfig.objects.create(pk=1, power_per_doubling=10)
        LevelPowerConfig.objects.create(pk=1, character_level_bonus=10, technique_level_bonus=0)

        sheet = CharacterSheetFactory()
        CharacterClassLevelFactory(character=sheet, level=1)
        cap = CapabilityTypeFactory(innate_baseline=0)
        self._trait_capability_grant(sheet=sheet, level=10, capability=cap)

        curved_value = sheet.character.threads.passive_capability_grants()[cap.pk]
        # Confirm the curve is actually engaged for this setup, not incidentally 1.
        self.assertGreater(curved_value, 1)

        availability_value = get_all_capability_values(sheet)[cap.pk]
        agency_value = get_effective_capability_value(sheet, cap)

        self.assertEqual(availability_value, curved_value)
        self.assertEqual(availability_value, agency_value)

    def test_thread_without_a_grant_row_for_x_contributes_nothing_to_x(self) -> None:
        """Ratified scope rule: a thread moves a capability only if it GRANTS it."""
        sheet = CharacterSheetFactory()
        cap_granted = CapabilityTypeFactory()
        cap_ungranted = CapabilityTypeFactory()
        self._trait_capability_grant(sheet=sheet, level=10, capability=cap_granted)
        # No ThreadPullEffect row anywhere names cap_ungranted.

        granted = sheet.character.threads.passive_capability_grants()
        self.assertIn(cap_granted.pk, granted)
        self.assertNotIn(cap_ungranted.pk, granted)

    def test_covenant_role_m2m_capabilities_stay_flat_at_one(self) -> None:
        """#2022 role-granted capabilities have no thread and no level — never curved."""
        CapabilityPowerConfig.objects.create(pk=1, power_per_doubling=10)
        LevelPowerConfig.objects.create(pk=1, character_level_bonus=50, technique_level_bonus=0)

        sheet = CharacterSheetFactory()
        # Large nonzero power: if this path were curved, it would inflate far past 1.
        CharacterClassLevelFactory(character=sheet, level=5)
        role = CovenantRoleFactory()
        resonance = ResonanceFactory()
        cap = CapabilityTypeFactory()
        role.granted_capabilities.add(cap)

        # The handler requires at least one thread to not early-return.
        ThreadFactory(
            owner=sheet,
            resonance=resonance,
            target_kind=TargetKind.COVENANT_ROLE,
            target_trait=None,
            target_covenant_role=role,
            level=10,
        )
        CharacterCovenantRoleFactory(
            character_sheet=sheet,
            covenant=CovenantFactory(),
            covenant_role=role,
            engaged=True,
            left_at=None,
        )

        granted = sheet.character.threads.passive_capability_grants()
        self.assertEqual(granted[cap.pk], 1)

    def test_returns_capability_pks_as_keys(self) -> None:
        """``set(handler.passive_capability_grants())`` must still yield CapabilityType pks.

        ``world.covenants.services`` (lines ~737, 772, 900) depends on exactly that
        shape — dict iteration yields keys, so wrapping the call in ``set(...)``
        keeps working unchanged.
        """
        sheet = CharacterSheetFactory()
        cap = CapabilityTypeFactory()
        self._trait_capability_grant(sheet=sheet, level=10, capability=cap)

        granted = sheet.character.threads.passive_capability_grants()
        self.assertIsInstance(granted, dict)
        self.assertEqual(set(granted), {cap.pk})


class ThreadCapabilityGrantQueryCountTests(TestCase):
    """No N+1: value computation must not scale queries with thread/capability count.

    Uses ONE sheet/handler throughout (rather than comparing two different
    characters) so both measurements start from identical process-wide
    SharedMemoryModel cache warmth — e.g. ``LevelPowerConfig``/``AuraPowerConfig``
    singletons touched by ``context_free_power``'s ``_derive_power`` call warm on
    first touch and would otherwise cost an extra query for whichever character
    happens to be measured first, which is a caching artifact, not the N+1 this
    test exists to catch.
    """

    @staticmethod
    def _add_grant(sheet) -> None:
        """Add one more independent TRAIT thread + tier-0 CAPABILITY_GRANT row.

        Each call uses its own resonance/capability — no shared effect row, so
        nothing here collapses to one query by coincidence.
        """
        resonance = ResonanceFactory()
        cap = CapabilityTypeFactory()
        ThreadFactory(owner=sheet, resonance=resonance, level=10)
        ThreadPullEffectFactory(
            target_kind=TargetKind.TRAIT,
            resonance=resonance,
            tier=0,
            min_thread_level=0,
            effect_kind=EffectKind.CAPABILITY_GRANT,
            flat_bonus_amount=None,
            capability_grant=cap,
        )

    def test_query_count_does_not_scale_with_thread_or_capability_count(self) -> None:
        CapabilityPowerConfig.objects.create(pk=1, power_per_doubling=10)
        sheet = CharacterSheetFactory()
        handler = sheet.character.threads

        self._add_grant(sheet)
        handler.passive_capability_grants()  # warm every process-wide singleton lookup
        handler.invalidate()

        with CaptureQueriesContext(connection) as baseline_ctx:
            handler.passive_capability_grants()
        baseline_count = len(baseline_ctx.captured_queries)
        self.assertGreater(baseline_count, 0)

        for _ in range(5):
            self._add_grant(sheet)
        handler.invalidate()

        with CaptureQueriesContext(connection) as scaled_ctx:
            handler.passive_capability_grants()

        self.assertEqual(baseline_count, len(scaled_ctx.captured_queries))


class CapabilityEffectSeverityScalingTests(TestCase):
    """#2708 Task 7: ConditionCapabilityEffect.scales_with_severity is honoured
    by get_capability_status, mirroring get_condition_modifier_total's
    precedence (severity branch wins; stage multiplier is the elif — never
    both, since ConditionInstance.effective_severity already folds the stage
    multiplier in).
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character

    def test_flag_false_ignores_severity(self) -> None:
        """Default False: an existing row's behaviour is bit-for-bit unchanged."""
        cap = CapabilityTypeFactory(name="sev_scale_off")
        condition = ConditionTemplateFactory(name="sev_scale_off_condition")
        ConditionCapabilityEffectFactory(
            condition=condition, capability=cap, value=5, scales_with_severity=False
        )
        apply_condition(target=self.character, condition=condition, severity=3)

        status = get_capability_status(self.sheet, cap)
        self.assertEqual(status.value, 5)

    def test_flag_true_scales_by_effective_severity(self) -> None:
        """A severity-3 instance of a +5 effect contributes +15."""
        cap = CapabilityTypeFactory(name="sev_scale_on")
        condition = ConditionTemplateFactory(name="sev_scale_on_condition")
        ConditionCapabilityEffectFactory(
            condition=condition, capability=cap, value=5, scales_with_severity=True
        )
        apply_condition(target=self.character, condition=condition, severity=3)

        status = get_capability_status(self.sheet, cap)
        self.assertEqual(status.value, 15)

    def test_stage_multiplier_precedence_matches_sibling(self) -> None:
        """Same precedence as get_condition_modifier_total:1758-1761 — the
        scales_with_severity branch wins, the stage branch is the elif, so a
        staged instance with the flag set does NOT also apply the stage
        multiplier on top of effective_severity (which already folds it in).
        """
        cap = CapabilityTypeFactory(name="sev_scale_precedence")
        progressive = ConditionTemplateFactory(
            name="sev_scale_precedence_cond", has_progression=True
        )
        stage = ConditionStageFactory(
            condition=progressive, stage_order=2, severity_multiplier=Decimal("2.0")
        )
        ConditionCapabilityEffectFactory(
            condition=progressive, capability=cap, value=10, scales_with_severity=True
        )
        instance = ConditionInstanceFactory(
            target=self.character, condition=progressive, current_stage=stage, severity=3
        )
        # effective_severity already folds the stage multiplier: 3 * 2.0 = 6.
        self.assertEqual(instance.effective_severity, 6)

        status = get_capability_status(self.sheet, cap)
        # Correct precedence: 10 * 6 = 60. A double-count bug (also applying
        # the stage multiplier on top) would instead produce 10 * 6 * 2 = 120.
        self.assertEqual(status.value, 60)


class CapabilityEffectSeverityScalingCrossReaderTests(TestCase):
    """#2708 Task 7 review: the availability oracle and the character-sheet
    display aggregation read the SAME ConditionCapabilityEffect rows as the
    agency oracle (get_capability_status) and must apply the identical
    scales_with_severity precedence, or they silently diverge from the check
    that actually resolves.

    - get_all_capability_values feeds the availability oracle
      (mechanics._get_condition_sources -> action discovery/gating).
    - views._aggregate_capability_effects feeds CharacterConditionsViewSet.summary,
      the endpoint a player's capability breakdown display reads.

    Both assertions compare oracle-to-oracle rather than to a hardcoded
    constant, so the guard survives retuning the curve.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character

    def test_availability_oracle_matches_agency_oracle_for_severity_scaled_effect(
        self,
    ) -> None:
        cap = CapabilityTypeFactory(name="sev_scale_availability")
        condition = ConditionTemplateFactory(name="sev_scale_availability_condition")
        ConditionCapabilityEffectFactory(
            condition=condition, capability=cap, value=5, scales_with_severity=True
        )
        apply_condition(target=self.character, condition=condition, severity=4)

        agency_value = get_capability_status(self.sheet, cap).value
        availability_value = get_all_capability_values(self.sheet)[cap.pk]

        self.assertEqual(availability_value, agency_value)

    def test_views_aggregation_matches_agency_oracle_for_severity_scaled_effect(
        self,
    ) -> None:
        cap = CapabilityTypeFactory(name="sev_scale_views")
        condition = ConditionTemplateFactory(name="sev_scale_views_condition")
        ConditionCapabilityEffectFactory(
            condition=condition, capability=cap, value=5, scales_with_severity=True
        )
        result = apply_condition(target=self.character, condition=condition, severity=4)
        assert result.instance is not None

        agency_value = get_capability_status(self.sheet, cap).value

        lookups = _build_effect_lookups([result.instance])
        summary = _aggregate_capability_effects(lookups)

        self.assertEqual(summary.values[cap.name], agency_value)


class ActionContextThreadingTests(TestCase):
    """#2708 Task 8: get_effective_capability_value(..., action_ctx=...).

    A TRAIT-kind thread's tier-0 INTENSITY_BUMP can only raise a technique
    grant's power — and therefore its curved value — when the caller supplies
    an ``action_ctx`` naming the trait. The ambient default (no action_ctx)
    deliberately cannot demonstrate the trait, so it stays dark. This is the
    "climbing" case from the #2708 design: a rope-and-pulley TRAIT thread
    should only light up during an actual climb.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()

    def _trait_thread_technique_setup(self) -> tuple[CapabilityType, Thread]:
        """A technique whose capability grant curves with power, plus a TRAIT
        thread carrying a tier-0 INTENSITY_BUMP that only feeds that power when
        the trait is named in a supplied action_ctx.
        """
        cap = CapabilityTypeFactory(innate_baseline=0)
        technique = TechniqueFactory(intensity=0)
        TechniqueCapabilityGrantFactory(
            technique=technique, capability=cap, base_value=1, intensity_multiplier=1
        )
        CharacterTechniqueFactory(character=self.sheet, technique=technique)

        resonance = ResonanceFactory()
        thread = ThreadFactory(owner=self.sheet, resonance=resonance, level=10)
        ThreadPullEffectFactory(
            target_kind=TargetKind.TRAIT,
            resonance=resonance,
            tier=0,
            min_thread_level=0,
            as_intensity_bump=True,
            intensity_bump_amount=50,
        )
        return cap, thread

    def test_default_context_excludes_trait_threads(self) -> None:
        """No action context: a TRAIT thread cannot be demonstrated, so it stays dark."""
        cap, _thread = self._trait_thread_technique_setup()

        result = get_effective_capability_value(self.sheet, cap)

        # power = technique.intensity(0) + context_free_power(0, no config) +
        # contextual_thread_power(0, trait not named) -> base_value(1) + 1*0 = 1.
        self.assertEqual(result, 1)

    def test_supplied_context_activates_trait_thread(self) -> None:
        """The climbing case: an action that involves the trait lights its thread up.

        This test exercises the curve itself (#2708's core feature), so it must
        create a ``CapabilityPowerConfig`` row — without one, the curve is disabled
        and this shape asserts nothing about it (#2708 C1 review: this test used to
        assert the additive value 51 with NO config row present, which was only
        possible because the oracle was wrongly feeding a real power figure through
        the retired additive formula. See
        ``InertOracleAtNonzeroSensitivityTests`` below for the inert-through-the-
        oracle guard that shape was missing.)
        """
        CapabilityPowerConfig.objects.create(pk=1)
        cap, thread = self._trait_thread_technique_setup()
        action_ctx = PullActionContext(involved_traits=(thread.target_trait_id,))

        result = get_effective_capability_value(self.sheet, cap, action_ctx=action_ctx)

        # power = 0 + 0 + 50 (tier-0 bump at thread level 10, multiplier 1.0).
        # Curved (default power_per_doubling=10): base_value(1) * 2 ** (sensitivity(1)
        # * power(50) / 10) = 1 * 2**5 = 32.
        self.assertEqual(result, 32)
        dark_value = get_effective_capability_value(self.sheet, cap)
        self.assertGreater(result, dark_value)

    def test_every_existing_caller_signature_still_works(self) -> None:
        """The param is keyword-only with a default; positional calls are unaffected."""
        cap = CapabilityTypeFactory(name="positional_call_still_works", innate_baseline=1)

        result = get_effective_capability_value(self.sheet, cap)

        self.assertEqual(result, 1)

    def test_caller_naming_one_technique_does_not_leak_into_another(self) -> None:
        """#2708 Task 8 review: naming T1 must not empower T2's grant via T1's thread.

        T1 and T2 both grant capability ``cap``. Only T1 has a TECHNIQUE-kind thread
        (a large tier-0 INTENSITY_BUMP). T1's own grant has intensity_multiplier=0, so
        its value is unaffected by power either way — T1's own self-anchoring (a
        technique's context always names itself, unchanged since before this task)
        cannot be what moves the result. T2's grant has intensity_multiplier=1, so if
        T1's thread leaks into T2's per-technique context (the bug: the caller's whole
        ``involved_techniques`` used to be merged into every technique's context,
        instead of narrowing to just the technique being evaluated), T2's grant value
        jumps and wins the cross-grant max(). A caller honestly naming "T1 is in play"
        must not inflate a capability T2 grants.
        """
        cap = CapabilityTypeFactory(innate_baseline=0)
        t1 = TechniqueFactory(intensity=0)
        t2 = TechniqueFactory(intensity=0)
        TechniqueCapabilityGrantFactory(
            technique=t1, capability=cap, base_value=1, intensity_multiplier=0
        )
        TechniqueCapabilityGrantFactory(
            technique=t2, capability=cap, base_value=1, intensity_multiplier=1
        )
        CharacterTechniqueFactory(character=self.sheet, technique=t1)
        CharacterTechniqueFactory(character=self.sheet, technique=t2)

        resonance = ResonanceFactory()
        ThreadFactory(
            owner=self.sheet,
            resonance=resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_technique=t1,
            target_trait=None,
            level=10,
        )
        ThreadPullEffectFactory(
            target_kind=TargetKind.TECHNIQUE,
            resonance=resonance,
            tier=0,
            min_thread_level=0,
            as_intensity_bump=True,
            intensity_bump_amount=50,
        )

        action_ctx = PullActionContext(involved_techniques=(t1.pk,))

        result = get_effective_capability_value(self.sheet, cap, action_ctx=action_ctx)

        # T1's own iteration: power=50 (self-anchored, as always), but
        # multiplier=0 -> value = base_value(1) + 0*50 = 1.
        # T2's iteration: T1's thread must NOT be visible here -> power=0 ->
        # value = base_value(1) + 1*0 = 1.
        # max(1, 1) = 1. Before the fix, T2's iteration saw T1's thread too
        # (ctx.involved_techniques=(T2, T1)), giving T2 a value of 51 and a
        # result of 51 — this assertion is what catches that regression.
        self.assertEqual(result, 1)


class InertOracleAtNonzeroSensitivityTests(TestCase):
    """#2708 C1 review: the shape nothing covered before this fix.

    Every other inert-invariant test either used ``intensity_multiplier=0`` (so a
    real power figure couldn't move the result even if fed through) or called
    ``calculate_value()`` bare directly (which never exercised the oracle's own
    power-derivation wiring at all). This is the one shape that combines a
    NONZERO sensitivity grant with an AMBIENTLY-active bumped thread and goes
    through the real oracle (``get_effective_capability_value``) with no
    ``CapabilityPowerConfig`` row present — exactly the state #2708 ships in. Before
    the fix, the oracle unconditionally computed
    ``technique.intensity + context_free_power + contextual_thread_power(...)`` and
    fed it to the RETIRED additive formula as ``effective_power``, so the ambient
    thread's bump leaked into a value that should have been untouched.
    """

    def test_ambient_gift_thread_bump_does_not_move_the_inert_value(self) -> None:
        sheet = CharacterSheetFactory()
        cap = CapabilityTypeFactory(innate_baseline=0)
        gift = GiftFactory()
        technique = TechniqueFactory(gift=gift, intensity=3)
        TechniqueCapabilityGrantFactory(
            technique=technique, capability=cap, base_value=1, intensity_multiplier=1
        )
        CharacterTechniqueFactory(character=sheet, technique=technique)

        # A GIFT thread is always in-action (_ALWAYS_IN_ACTION_KINDS), so this bump
        # is visible even under the ambient default (no action_ctx) — the shape most
        # likely to fire on every ordinary capability read post-merge.
        thread = ThreadFactory(
            owner=sheet,
            target_kind=TargetKind.GIFT,
            target_gift=gift,
            target_trait=None,
            level=20,
        )
        ThreadPullEffectFactory(
            target_kind=TargetKind.GIFT,
            resonance=thread.resonance,
            target_gift=gift,
            tier=0,
            as_intensity_bump=True,
            intensity_bump_amount=100,
        )

        result = get_effective_capability_value(sheet, cap)

        # No CapabilityPowerConfig row: the curve is disabled, and the ambient
        # thread's bump must be invisible to the RETIRED additive formula — the
        # exact pre-#2708 number, computed from technique.intensity alone:
        # base_value(1) + intensity_multiplier(1) * technique.intensity(3) = 4.
        self.assertEqual(result, 4)


class CapabilityOracleQueryCountTests(TestCase):
    """#2708 Task 8: the regression guard for the whole caching design.

    Uses ONE sheet/handler throughout (mirrors ``ThreadCapabilityGrantQueryCountTests``
    above) so measurements start from identical process-wide SharedMemoryModel cache
    warmth rather than an artifact of which character happens to be measured first.
    """

    @staticmethod
    def _add_known_technique(sheet, cap: CapabilityType) -> None:
        """Add one more independently-known technique granting ``cap``."""
        technique = TechniqueFactory(intensity=1)
        TechniqueCapabilityGrantFactory(
            technique=technique, capability=cap, base_value=1, intensity_multiplier=0
        )
        CharacterTechniqueFactory(character=sheet, technique=technique)

    def test_sweeping_many_techniques_is_constant_query(self) -> None:
        """Ten known techniques must not cost ten derivations."""
        sheet = CharacterSheetFactory()
        cap = CapabilityTypeFactory(innate_baseline=0)
        handler = sheet.character.threads

        self._add_known_technique(sheet, cap)
        self._add_known_technique(sheet, cap)
        get_effective_capability_value(sheet, cap)  # warm every process-wide singleton
        handler.invalidate()

        with CaptureQueriesContext(connection) as two_ctx:
            get_effective_capability_value(sheet, cap)
        two_count = len(two_ctx.captured_queries)
        self.assertGreater(two_count, 0)

        for _ in range(8):
            self._add_known_technique(sheet, cap)
        handler.invalidate()

        with CaptureQueriesContext(connection) as ten_ctx:
            get_effective_capability_value(sheet, cap)

        self.assertEqual(two_count, len(ten_ctx.captured_queries))

    def test_action_ctx_does_not_increase_query_count(self) -> None:
        """Supplying action_ctx costs no more than the ambient default, and repeated
        reads with the same action_ctx stay flat rather than re-deriving anything.
        """
        sheet = CharacterSheetFactory()
        cap = CapabilityTypeFactory(innate_baseline=0)
        handler = sheet.character.threads
        self._add_known_technique(sheet, cap)
        self._add_known_technique(sheet, cap)
        get_effective_capability_value(sheet, cap)  # warm every process-wide singleton
        handler.invalidate()

        with CaptureQueriesContext(connection) as ambient_ctx:
            get_effective_capability_value(sheet, cap)
        ambient_count = len(ambient_ctx.captured_queries)
        self.assertGreater(ambient_count, 0)
        handler.invalidate()

        action_ctx = PullActionContext(involved_traits=(1,), involved_objects=(1,))
        with CaptureQueriesContext(connection) as first_ctx:
            get_effective_capability_value(sheet, cap, action_ctx=action_ctx)
        first_count = len(first_ctx.captured_queries)
        self.assertLessEqual(first_count, ambient_count)
        handler.invalidate()

        with CaptureQueriesContext(connection) as second_ctx:
            get_effective_capability_value(sheet, cap, action_ctx=action_ctx)
        second_count = len(second_ctx.captured_queries)

        self.assertEqual(first_count, second_count)
