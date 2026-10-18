"""Whoever plays a story NPC is not offered templates the NPC cannot use (#4418)."""

from __future__ import annotations

from django.test import TestCase

from actions.constants import ActionCategory, ActionTargetType
from actions.factories import ActionTemplateFactory
from actions.player_interface import get_player_actions
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.consent.factories import make_general_category
from world.roster.factories import RosterEntryFactory
from world.roster.models.choices import RosterType


class NpcSceneActionsTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = ActionTemplateFactory(
            name="Deceive",
            category=ActionCategory.SOCIAL,
            target_type=ActionTargetType.SINGLE,
        )
        cls.pc = CharacterSheetFactory().character
        npc_entry = RosterEntryFactory(roster__roster_type=RosterType.NPC)
        cls.npc = npc_entry.character_sheet.character

    def _names(self, character) -> set[str]:
        return {a.display_name for a in get_player_actions(character)}

    def test_npc_is_not_offered_unresisted_templates(self) -> None:
        self.assertNotIn("Deceive", self._names(self.npc))
        self.assertIn("Deceive", self._names(self.pc))

    def test_npc_is_offered_the_template_once_authored(self) -> None:
        self.template.resist_check_type = CheckTypeFactory()
        self.template.consent_category = make_general_category()
        self.template.save()
        self.assertIn("Deceive", self._names(self.npc))

    def test_npc_is_not_offered_an_untagged_template_even_with_a_resist(self) -> None:
        self.template.resist_check_type = CheckTypeFactory()
        self.template.save()
        self.assertNotIn("Deceive", self._names(self.npc))
