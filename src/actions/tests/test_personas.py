"""Tests for SetActivePersonaAction (#1347)."""

from django.test import TestCase

from actions.definitions.personas import SetActivePersonaAction
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.constants import PersonaType
from world.scenes.factories import PersonaFactory
from world.scenes.services import ActivePersonaError, active_persona_for_sheet


class SetActivePersonaActionTests(TestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.alt = PersonaFactory(
            character_sheet=self.sheet, persona_type=PersonaType.ESTABLISHED, name="Alt Face"
        )

    def test_switches_to_owned_persona(self) -> None:
        result = SetActivePersonaAction().run(actor=self.character, persona_id=self.alt.pk)
        self.assertTrue(result.success)
        self.sheet.refresh_from_db()
        self.assertEqual(active_persona_for_sheet(self.sheet), self.alt)
        self.assertEqual(result.data["active_persona_id"], self.alt.pk)

    def test_rejects_foreign_persona_uniform_message(self) -> None:
        other = CharacterSheetFactory()
        foreign = other.primary_persona
        result = SetActivePersonaAction().run(actor=self.character, persona_id=foreign.pk)
        self.assertFalse(result.success)
        self.assertIn("isn't one of this character's identities", result.message)
        self.sheet.refresh_from_db()
        self.assertEqual(active_persona_for_sheet(self.sheet), self.sheet.primary_persona)

    def test_rejects_unknown_id(self) -> None:
        result = SetActivePersonaAction().run(actor=self.character, persona_id=999999)
        self.assertFalse(result.success)
        self.assertEqual(result.message, ActivePersonaError.user_message)
