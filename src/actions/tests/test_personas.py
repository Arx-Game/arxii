"""Tests for SetActivePersonaAction (#1347).

The happy-path switch (owned persona) and foreign-persona rejection are
covered by the E2E journey test ``test_persona_telnet_e2e.py``
(``test_telnet_list_then_switch`` and ``test_foreign_persona_rejected_via_telnet``).
This test retains only the edge case the journey does NOT cover: an unknown
persona id (non-existent pk).
"""

from django.test import TestCase

from actions.definitions.personas import SetActivePersonaAction
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.services import ActivePersonaError


class SetActivePersonaActionTests(TestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character

    def test_rejects_unknown_id(self) -> None:
        result = SetActivePersonaAction().run(actor=self.character, persona_id=999999)
        self.assertFalse(result.success)
        self.assertEqual(result.message, ActivePersonaError.user_message)
