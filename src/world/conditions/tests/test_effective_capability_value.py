from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassLevelFactory
from world.conditions.factories import (
    CapabilityTypeFactory,
    ConditionCapabilityEffectFactory,
    ConditionTemplateFactory,
)
from world.conditions.models import CapabilityType
from world.conditions.services import apply_condition, get_effective_capability_value
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
)
from world.magic.constants import EffectKind, TargetKind
from world.magic.factories import (
    CharacterTechniqueFactory,
    ResonanceFactory,
    TechniqueCapabilityGrantFactory,
    TechniqueFactory,
    ThreadFactory,
    ThreadPullEffectFactory,
)
from world.magic.models import CapabilityPowerConfig, LevelPowerConfig
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
