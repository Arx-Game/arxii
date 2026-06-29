"""Capability gate for the at-will ``shift_form`` action (#1604 Task 4)."""

from django.test import TestCase

from actions.definitions.forms import ShiftFormAction
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import CapabilityTypeFactory
from world.forms.factories import (
    AlternateSelfFactory,
    CharacterFormFactory,
    CharacterFormStateFactory,
)
from world.forms.models import FormType
from world.mechanics.factories import ModifierCategoryFactory, ModifierSourceFactory
from world.mechanics.models import CharacterModifier, ModifierTarget

AT_WILL_SHIFTING = "at_will_shifting"


class ShiftFormCapabilityGateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character
        true_form = CharacterFormFactory(character=cls.character, form_type=FormType.TRUE)
        cls.alt_form = CharacterFormFactory(
            character=cls.character, name="Beast", form_type=FormType.ALTERNATE
        )
        CharacterFormStateFactory(character=cls.character, active_form=true_form)
        cls.alt_self = AlternateSelfFactory(
            character=cls.sheet, form=cls.alt_form, display_name="the Beast"
        )
        cls.capability = CapabilityTypeFactory(name=AT_WILL_SHIFTING, innate_baseline=0)

    def _grant_capability(self):
        category = ModifierCategoryFactory(name="capability")
        target = ModifierTarget.objects.create(
            name=f"capability_{self.capability.pk}",
            category=category,
            target_capability=self.capability,
        )
        source = ModifierSourceFactory()
        CharacterModifier.objects.create(
            character=self.sheet,
            target=target,
            source=source,
            value=1,
        )

    def test_shift_fails_without_at_will_shifting(self):
        result = ShiftFormAction().run(actor=self.character, alternate_self_id=self.alt_self.pk)

        self.assertFalse(result.success)
        self.assertIn("shift", result.message.lower())

    def test_shift_succeeds_with_at_will_shifting(self):
        self._grant_capability()

        result = ShiftFormAction().run(actor=self.character, alternate_self_id=self.alt_self.pk)

        self.assertTrue(result.success)
