"""Tests for Audere/Audere Majora power-multiplier spike in _derive_power (#636)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import (
    ConditionModifierEffectFactory,
    ConditionTemplateFactory,
)
from world.conditions.services import apply_condition, remove_condition
from world.magic.factories import (
    TechniqueFactory,
    wire_audere_power_multipliers,
)
from world.magic.services.techniques import _derive_power, get_runtime_technique_stats
from world.mechanics.constants import POWER_CATEGORY_NAME, POWER_MULTIPLIER_TARGET_NAME
from world.mechanics.factories import GlobalPowerTargetFactory, PowerMultiplierTargetFactory


class PowerMultiplierTargetFactoryTests(TestCase):
    def test_power_multiplier_target_factory_is_in_power_category(self):
        t = PowerMultiplierTargetFactory()
        self.assertEqual(t.category.name, POWER_CATEGORY_NAME)
        self.assertEqual(t.name, POWER_MULTIPLIER_TARGET_NAME)


class DerivePowerConditionContributionTests(TestCase):
    """_derive_power reads active-condition power contributions (#636 Task 6)."""

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character

    def _derive(self, channeled_intensity):
        return _derive_power(
            channeled_intensity=channeled_intensity, technique=None, character=self.character
        )

    def test_flat_condition_effect_raises_power_additively(self):
        target = GlobalPowerTargetFactory()
        condition = ConditionTemplateFactory(name="flat_power_cond")
        ConditionModifierEffectFactory(condition=condition, modifier_target=target, value=10)
        apply_condition(target=self.character, condition=condition)

        # round(100 * 100/100) + 10 = 110
        self.assertEqual(self._derive(100), 110)

    def test_multiplier_condition_effect_scales_intensity(self):
        target = PowerMultiplierTargetFactory()
        condition = ConditionTemplateFactory(name="mult_power_cond")
        ConditionModifierEffectFactory(condition=condition, modifier_target=target, value=35)
        apply_condition(target=self.character, condition=condition)

        # round(100 * (100+35)/100) + 0 = 135
        self.assertEqual(self._derive(100), 135)

    def test_two_multiplier_sources_sum_deltas(self):
        target = PowerMultiplierTargetFactory()
        cond_a = ConditionTemplateFactory(name="mult_a")
        cond_b = ConditionTemplateFactory(name="mult_b")
        ConditionModifierEffectFactory(condition=cond_a, modifier_target=target, value=35)
        ConditionModifierEffectFactory(condition=cond_b, modifier_target=target, value=50)
        apply_condition(target=self.character, condition=cond_a)
        apply_condition(target=self.character, condition=cond_b)

        # round(100 * (100+85)/100) = 185
        self.assertEqual(self._derive(100), 185)

    def test_removing_condition_removes_power_contribution(self):
        target = PowerMultiplierTargetFactory()
        condition = ConditionTemplateFactory(name="mult_removed")
        ConditionModifierEffectFactory(condition=condition, modifier_target=target, value=100)
        apply_condition(target=self.character, condition=condition)
        self.assertEqual(self._derive(10), 20)

        remove_condition(target=self.character, condition=condition)
        self.assertEqual(self._derive(10), 10)

    def test_floor_at_zero_preserved(self):
        target = PowerMultiplierTargetFactory()
        condition = ConditionTemplateFactory(name="neg_mult")
        ConditionModifierEffectFactory(condition=condition, modifier_target=target, value=-500)
        apply_condition(target=self.character, condition=condition)

        # round(10 * (100-500)/100) = -40 → floored to 0
        self.assertEqual(self._derive(10), 0)


class AuderePowerSpikeTests(TestCase):
    """Audere / Audere Majora seed conditions land harder without touching cost (#636 Task 7)."""

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character
        cls.audere, cls.majora = wire_audere_power_multipliers()

    def _derive(self, channeled_intensity):
        return _derive_power(
            channeled_intensity=channeled_intensity, technique=None, character=self.character
        )

    def test_wiring_is_idempotent(self):
        # A second call must not raise (unique constraint) nor change the delta.
        wire_audere_power_multipliers()
        apply_condition(target=self.character, condition=self.audere)
        self.assertEqual(self._derive(10), 20)

    def test_audere_active_doubles_power(self):
        apply_condition(target=self.character, condition=self.audere)
        # delta 100 → ×2
        self.assertEqual(self._derive(10), 20)

    def test_audere_majora_triples_power(self):
        apply_condition(target=self.character, condition=self.majora)
        # delta 200 → ×3
        self.assertEqual(self._derive(10), 30)

    def test_majora_spike_strictly_larger_than_audere(self):
        audere_sheet = CharacterSheetFactory()
        majora_sheet = CharacterSheetFactory()
        apply_condition(target=audere_sheet.character, condition=self.audere)
        apply_condition(target=majora_sheet.character, condition=self.majora)

        audere_power = _derive_power(
            channeled_intensity=10, technique=None, character=audere_sheet.character
        )
        majora_power = _derive_power(
            channeled_intensity=10, technique=None, character=majora_sheet.character
        )
        self.assertGreater(majora_power, audere_power)

    def test_spike_does_not_change_channeled_cost_inputs(self):
        """Power rises, but runtime intensity/control (the anima/mishap/Soulfray
        cost drivers) are identical with and without the Audere spike."""
        technique = TechniqueFactory()
        before = get_runtime_technique_stats(technique, self.character)
        apply_condition(target=self.character, condition=self.audere)
        after = get_runtime_technique_stats(technique, self.character)

        self.assertEqual(before.intensity, after.intensity)
        self.assertEqual(before.control, after.control)
        # ...while derived power with the same channeled intensity is spiked.
        self.assertEqual(self._derive(10), 20)
