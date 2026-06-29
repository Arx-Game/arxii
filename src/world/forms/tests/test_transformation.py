from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.forms.factories import (
    AlternateSelfFactory,
    CharacterFormFactory,
    CharacterFormStateFactory,
    FormCombatProfileEffectFactory,
    FormCombatProfileFactory,
)
from world.forms.models import FormType
from world.forms.services.transformation import SCALE, trigger_transformation
from world.mechanics.factories import ModifierTargetFactory
from world.mechanics.models import CharacterModifier, ModifierSource
from world.scenes.factories import PersonaFactory


class TriggerTransformationVarianceTests(TestCase):
    """Tests for the trigger_transformation seam and tuning_value variance."""

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.true_form = CharacterFormFactory(
            character=cls.sheet.character, name="True", form_type=FormType.TRUE
        )
        cls.alt_form = CharacterFormFactory(
            character=cls.sheet.character, name="Beast", form_type=FormType.ALTERNATE
        )
        CharacterFormStateFactory(character=cls.sheet.character, active_form=cls.true_form)
        PersonaFactory(character_sheet=cls.sheet)
        cls.profile = FormCombatProfileFactory(form=cls.alt_form)
        cls.target = ModifierTargetFactory()
        cls.effect = FormCombatProfileEffectFactory(
            profile=cls.profile, target=cls.target, value=30
        )

    def _latest_source(self):
        return (
            ModifierSource.objects.filter(form_combat_profile=self.profile).order_by("-id").first()
        )

    def _modifier_value(self):
        source = self._latest_source()
        self.assertIsNotNone(source)
        modifier = CharacterModifier.objects.get(source=source, target=self.target)
        return modifier.value

    def test_trigger_transformation_applies_baseline_tuning(self):
        """A tuned alt-self applies baseline tuning to its granted modifiers."""
        alt = AlternateSelfFactory(
            character=self.sheet,
            combat_profile=self.profile,
            tuning_value=2,
        )

        trigger_transformation(self.sheet, alt, cause="test")

        # 30 * 2 * 1.0 / 10 == 6.0
        self.assertEqual(self._modifier_value(), 6)

    def test_tuning_value_individualizes_shared_form(self):
        """Two alts sharing one profile with different tuning_values produce different grants."""
        alt_a = AlternateSelfFactory(
            character=self.sheet,
            combat_profile=self.profile,
            tuning_value=2,
        )
        alt_b = AlternateSelfFactory(
            character=self.sheet,
            combat_profile=self.profile,
            tuning_value=3,
        )

        trigger_transformation(self.sheet, alt_a, cause="test")
        value_a = self._modifier_value()

        # Revert so the second assumption can run.
        from world.forms.services import revert_alternate_self

        revert_alternate_self(self.sheet)

        trigger_transformation(self.sheet, alt_b, cause="test")
        value_b = self._modifier_value()

        self.assertEqual(value_a, 6)  # 30 * 2 * 1.0 / 10
        self.assertEqual(value_b, 9)  # 30 * 3 * 1.0 / 10
        self.assertNotEqual(value_a, value_b)

    def test_instance_value_scales_per_assumption(self):
        """The instance_value multiplier produces different grants for the same alt."""
        alt = AlternateSelfFactory(
            character=self.sheet,
            combat_profile=self.profile,
            tuning_value=2,
        )

        trigger_transformation(self.sheet, alt, cause="test", instance_value=1.0)
        value_default = self._modifier_value()

        from world.forms.services import revert_alternate_self

        revert_alternate_self(self.sheet)

        trigger_transformation(self.sheet, alt, cause="test", instance_value=1.5)
        value_scaled = self._modifier_value()

        # 30 * 2 * 1.0 / 10 == 6.0
        # 30 * 2 * 1.5 / 10 == 9.0
        self.assertEqual(value_default, 6)
        self.assertEqual(value_scaled, 9)
        self.assertNotEqual(value_default, value_scaled)

    def test_neutral_factors_reproduce_effect_value(self):
        """Default factors (tuning_value=None, instance_value=1.0) do not alter the effect value."""
        alt = AlternateSelfFactory(
            character=self.sheet,
            combat_profile=self.profile,
            tuning_value=None,
        )

        trigger_transformation(self.sheet, alt, cause="test", instance_value=1.0)

        self.assertEqual(self._modifier_value(), self.effect.value)

    def test_scale_constant_value(self):
        """SCALE is 10 as required by the spec."""
        self.assertEqual(SCALE, 10)
