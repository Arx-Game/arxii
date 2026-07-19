from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import (
    CapabilityTypeFactory,
    ConditionCapabilityEffectFactory,
    ConditionTemplateFactory,
)
from world.conditions.models import CapabilityType
from world.conditions.services import apply_condition, get_effective_capability_value
from world.magic.factories import (
    CharacterTechniqueFactory,
    TechniqueCapabilityGrantFactory,
    TechniqueFactory,
)
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
