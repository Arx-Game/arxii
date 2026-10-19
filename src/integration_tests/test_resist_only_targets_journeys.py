"""A PC extra target of a played NPC's action sees whether it can be refused (#4418)."""

from __future__ import annotations

from actions.constants import ActionCategory, ActionTargetType
from actions.factories import ActionTemplateFactory
from integration_tests.harness import JourneyCase
from world.checks.factories import CheckTypeFactory
from world.consent.factories import SocialConsentCategoryFactory
from world.roster.factories import RosterFactory
from world.roster.models.choices import RosterType
from world.scenes.action_services import create_action_request
from world.scenes.factories import SceneFactory

SOCIAL = {"category": ActionCategory.SOCIAL, "target_type": ActionTargetType.SINGLE}


def persona_of(character):
    return character.sheet_data.primary_persona


class ThePendingTargetsShowWhatCanBeRefused(JourneyCase):
    """Hobb is a major NPC a GM plays; Ysmay is his primary target, Wren an extra one."""

    def setUp(self) -> None:
        super().setUp()
        self.room = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.wren = self.make_player("Wren", room=self.room)
        self.hobb = self.make_player("Hobb", room=self.room)
        self.hobb.sheet_data.roster_entry.move_to_roster(RosterFactory(roster_type=RosterType.NPC))
        self.scene = SceneFactory(room=self.room)
        check_type = CheckTypeFactory(name="Persuasion")
        self.composure = CheckTypeFactory(name="Composure")
        ActionTemplateFactory(
            name="Deceive",
            consent_category=SocialConsentCategoryFactory(key="manipulative", name="Manipulative"),
            check_type=check_type,
            resist_check_type=self.composure,
            **SOCIAL,
        )
        romantic = SocialConsentCategoryFactory(key="romantic", name="Romantic")
        romantic.refusable_from_npcs = True
        romantic.save()
        ActionTemplateFactory(
            name="Flirt",
            check_type=check_type,
            resist_check_type=self.composure,
            consent_category=romantic,
            **SOCIAL,
        )

    def _wrens_pending_target(self, action_key: str) -> dict:
        create_action_request(
            scene=self.scene,
            initiator_persona=persona_of(self.hobb),
            target_persona=persona_of(self.ysmay),
            action_key=action_key,
            additional_target_personas=[persona_of(self.wren)],
        )
        response = self.api(self.account_of(self.wren)).get("/api/action-targets/?status=pending")
        self.assertEqual(response.status_code, 200)
        rows = response.json()["results"]
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_a_contested_action_is_resist_only_on_the_extra_target(self) -> None:
        row = self._wrens_pending_target("deceive")
        self.assertIs(row["resist_only"], True)
        self.assertEqual(row["resist_check_name"], "Composure")

    def test_a_romantic_action_can_still_be_refused(self) -> None:
        row = self._wrens_pending_target("flirt")
        self.assertIs(row["resist_only"], False)
        self.assertIsNone(row["resist_check_name"])
