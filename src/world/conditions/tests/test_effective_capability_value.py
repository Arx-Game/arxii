from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import (
    CapabilityTypeFactory,
    ConditionCapabilityEffectFactory,
    ConditionTemplateFactory,
)
from world.conditions.models import CapabilityType
from world.conditions.services import apply_condition, get_effective_capability_value
from world.mechanics.factories import ModifierCategoryFactory
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
