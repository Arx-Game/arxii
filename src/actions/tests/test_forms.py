"""Tests for ShiftFormAction and RevertFormAction (#1111 slice 4)."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.definitions.forms import (
    _NO_ACTIVE_ALT_SELF_ACTION_MSG,
    RevertFormAction,
    ShiftFormAction,
)
from evennia_extensions.factories import CharacterFactory
from world.character_sheets.models import CharacterSheet
from world.conditions.capability_content import AT_WILL_SHIFTING
from world.conditions.factories import CapabilityTypeFactory
from world.forms.factories import (
    AlternateSelfFactory,
    CharacterFormFactory,
    CharacterFormStateFactory,
    FormCombatProfileEffectFactory,
    FormCombatProfileFactory,
)
from world.forms.models import (
    ActiveAlternateSelf,
    AlternateSelf,
    CharacterForm,
    CharacterFormState,
    FormType,
)
from world.forms.services import RevertBlockedError, assume_alternate_self
from world.mechanics.factories import ModifierCategoryFactory, ModifierSourceFactory
from world.mechanics.models import CharacterModifier, ModifierSource, ModifierTarget


class ShiftFormActionTests(TestCase):
    def setUp(self) -> None:
        self.sheet = self._sheet()
        self.character = self.sheet.character
        true_form = self._make_form(self.character, form_type=FormType.TRUE)
        self.alt_form = self._make_form(self.character, name="Beast", form_type=FormType.ALTERNATE)
        CharacterFormStateFactory(character=self.character, active_form=true_form)
        self.alt = self._make_alt(self.sheet, form=self.alt_form, display_name="the Beast")
        self._grant_at_will_shifting()

    def _grant_at_will_shifting(self) -> None:
        capability = CapabilityTypeFactory(name=AT_WILL_SHIFTING, innate_baseline=0)
        category = ModifierCategoryFactory(name="capability")
        target = ModifierTarget.objects.create(
            name=f"capability_{capability.pk}",
            category=category,
            target_capability=capability,
        )
        source = ModifierSourceFactory()
        CharacterModifier.objects.create(
            character=self.sheet,
            target=target,
            source=source,
            value=1,
        )

    def _sheet(self) -> CharacterSheet:
        from world.character_sheets.factories import CharacterSheetFactory

        return CharacterSheetFactory()

    def _make_form(
        self, character, name: str = "", form_type: str = FormType.TRUE
    ) -> CharacterForm:
        return CharacterFormFactory(character=character, name=name, form_type=form_type)

    def _make_alt(self, sheet: CharacterSheet, **kwargs) -> AlternateSelf:
        return AlternateSelfFactory(character=sheet, **kwargs)

    def test_assumes_alternate_self(self) -> None:
        result = ShiftFormAction().run(actor=self.character, alternate_self_id=self.alt.pk)

        self.assertTrue(result.success)
        state = CharacterFormState.objects.get(character=self.character)
        self.assertEqual(state.active_form, self.alt_form)
        self.assertEqual(result.data["alternate_self_id"], self.alt.pk)

    def test_rejects_foreign_alternate_self_id(self) -> None:
        other_sheet = self._sheet()
        other_alt = self._make_alt(other_sheet)

        result = ShiftFormAction().run(actor=self.character, alternate_self_id=other_alt.pk)

        self.assertFalse(result.success)
        self.assertIn("alternate self", result.message.lower())

    def test_not_gated_by_in_control(self) -> None:
        fake_condition = MagicMock()
        fake_condition.condition.category.alters_behavior = True
        with patch.object(self.character.conditions, "active", return_value=[fake_condition]):
            result = ShiftFormAction().run(actor=self.character, alternate_self_id=self.alt.pk)

        self.assertTrue(result.success)

    def test_blocks_shift_over_active_alternate_self(self) -> None:
        # Assume a first alt-self, then try to shift to a second without reverting.
        first = ShiftFormAction().run(actor=self.character, alternate_self_id=self.alt.pk)
        self.assertTrue(first.success)
        # Give the second a combat profile so we can assert its grants weren't created.
        other_profile = FormCombatProfileFactory(form=self.alt_form)
        FormCombatProfileEffectFactory(profile=other_profile)
        other_alt = self._make_alt(
            self.sheet, form=self.alt_form, combat_profile=other_profile, display_name="the Wolf"
        )

        result = ShiftFormAction().run(actor=self.character, alternate_self_id=other_alt.pk)

        self.assertFalse(result.success)
        # The active alt-self is unchanged (the first one, not the second).
        active = ActiveAlternateSelf.objects.get(character=self.sheet)
        self.assertEqual(active.alternate_self, self.alt)
        # No grants (ModifierSource / CharacterModifier) were created for the
        # rejected second alt-self.
        self.assertFalse(ModifierSource.objects.filter(form_combat_profile=other_profile).exists())

    def test_shift_cross_sheet_persona_returns_safe_failure_not_500(self) -> None:
        # An AlternateSelf grant owned by this sheet, but whose persona FK points
        # at ANOTHER sheet (bad seed/admin edit). set_active_persona would raise
        # ActivePersonaError; the action must catch it and return a safe failure
        # rather than letting the ValueError propagate uncaught (-> 500 on web).
        from world.scenes.factories import PersonaFactory
        from world.scenes.services import ActivePersonaError

        other_sheet = self._sheet()
        foreign_persona = PersonaFactory(character_sheet=other_sheet)
        alt = self._make_alt(self.sheet, persona=foreign_persona, display_name="stolen face")

        result = ShiftFormAction().run(actor=self.character, alternate_self_id=alt.pk)

        self.assertFalse(result.success)
        self.assertEqual(result.message, ActivePersonaError.user_message)
        # The alt-self was not assumed.
        active = ActiveAlternateSelf.objects.filter(character=self.sheet).first()
        self.assertTrue(active is None or active.alternate_self_id is None)

    def test_shift_cross_sheet_form_returns_safe_failure_not_500(self) -> None:
        # Symmetric to the persona case: an AlternateSelf grant owned by this
        # sheet, but whose form FK points at ANOTHER character's CharacterForm
        # (bad seed/admin edit). switch_form would raise a bare ValueError;
        # the action must catch FormOwnershipError and return a safe failure
        # rather than letting the ValueError propagate uncaught (-> 500 on web).
        from world.forms.services import FormOwnershipError

        other_character = CharacterFactory()
        foreign_form = self._make_form(
            other_character, name="stranger", form_type=FormType.ALTERNATE
        )
        alt = self._make_alt(self.sheet, form=foreign_form, display_name="stolen shape")

        result = ShiftFormAction().run(actor=self.character, alternate_self_id=alt.pk)

        self.assertFalse(result.success)
        self.assertEqual(result.message, FormOwnershipError.user_message)


class RevertFormActionTests(TestCase):
    def setUp(self) -> None:
        self.sheet = self._sheet()
        self.character = self.sheet.character
        self.true_form = self._make_form(self.character, form_type=FormType.TRUE)
        self.alt_form = self._make_form(self.character, name="Beast", form_type=FormType.ALTERNATE)
        CharacterFormStateFactory(character=self.character, active_form=self.true_form)
        self.alt = self._make_alt(self.sheet, form=self.alt_form, display_name="the Beast")
        assume_alternate_self(self.sheet, self.alt)

    def _sheet(self) -> CharacterSheet:
        from world.character_sheets.factories import CharacterSheetFactory

        return CharacterSheetFactory()

    def _make_form(
        self, character, name: str = "", form_type: str = FormType.TRUE
    ) -> CharacterForm:
        return CharacterFormFactory(character=character, name=name, form_type=form_type)

    def _make_alt(self, sheet: CharacterSheet, **kwargs) -> AlternateSelf:
        return AlternateSelfFactory(character=sheet, **kwargs)

    def test_reverts_to_true_form(self) -> None:
        result = RevertFormAction().run(actor=self.character)

        self.assertTrue(result.success)
        state = CharacterFormState.objects.get(character=self.character)
        self.assertEqual(state.active_form, self.true_form)
        active = ActiveAlternateSelf.objects.get(character=self.sheet)
        self.assertIsNone(active.alternate_self)

    def test_blocked_when_not_in_control(self) -> None:
        fake_condition = MagicMock()
        fake_condition.condition.category.alters_behavior = True
        with patch.object(self.character.conditions, "active", return_value=[fake_condition]):
            result = RevertFormAction().run(actor=self.character)

        self.assertFalse(result.success)
        self.assertEqual(result.message, RevertBlockedError.user_message)

    def test_no_active_alternate_self(self) -> None:
        # Create a fresh character with no active alt-self.
        sheet = self._sheet()
        CharacterFormStateFactory(character=sheet.character, active_form=None)

        result = RevertFormAction().run(actor=sheet.character)

        self.assertFalse(result.success)
        # Locks the "never str(exc)" invariant: the safe constant, not the
        # exception's text, must reach the player.
        self.assertEqual(result.message, _NO_ACTIVE_ALT_SELF_ACTION_MSG)
