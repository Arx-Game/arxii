"""Tests for ShiftFormAction and RevertFormAction (#1111 slice 4)."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.definitions.forms import RevertFormAction, ShiftFormAction
from world.character_sheets.models import CharacterSheet
from world.forms.factories import (
    AlternateSelfFactory,
    CharacterFormFactory,
    CharacterFormStateFactory,
)
from world.forms.models import (
    ActiveAlternateSelf,
    AlternateSelf,
    CharacterForm,
    CharacterFormState,
    FormType,
)
from world.forms.services import RevertBlockedError, assume_alternate_self


class ShiftFormActionTests(TestCase):
    def setUp(self) -> None:
        self.sheet = self._sheet()
        self.character = self.sheet.character
        true_form = self._make_form(self.character, form_type=FormType.TRUE)
        self.alt_form = self._make_form(self.character, name="Beast", form_type=FormType.ALTERNATE)
        CharacterFormStateFactory(character=self.character, active_form=true_form)
        self.alt = self._make_alt(self.sheet, form=self.alt_form, display_name="the Beast")

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
