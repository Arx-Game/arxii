"""Journeys for playing the cast (#4418): a GM or Guide plays a major NPC in a scene."""

from __future__ import annotations

from rest_framework import status

from actions.factories import ActionTemplateFactory
from integration_tests.harness import JourneyCase
from world.battles.constants import BattleSideRole
from world.battles.resolution import select_surrounded_terminal_pool
from world.battles.services import add_place, add_side, create_battle, enlist_participant
from world.checks.factories import CheckTypeFactory
from world.consent.factories import SocialConsentCategoryFactory
from world.progression.models import WeeklySocialEngagement
from world.roster.factories import RosterFactory
from world.roster.models.choices import RosterType
from world.scenes.factories import SceneFactory
from world.vitals.constants import POOL_SURROUNDED_TERMINAL_ENEMY
from world.vitals.factories import ensure_surrounded_content


def persona_of(character):
    return character.sheet_data.primary_persona


class APlayedNpcIsAnNpc(JourneyCase):
    """Hobb is a major NPC a GM plays; Ysmay is a player character in the scene."""

    def setUp(self) -> None:
        super().setUp()
        self.room = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.hobb = self.make_player("Hobb", room=self.room)
        # Hobb is held by an account and puppeted, as a GM plays a major NPC.
        entry = self.hobb.sheet_data.roster_entry
        entry.move_to_roster(RosterFactory(roster_type=RosterType.NPC))
        self.scene = SceneFactory(room=self.room)
        ActionTemplateFactory(name="Persuade", check_type=CheckTypeFactory(name="Persuasion"))

    def test_persuade_lands_at_once_on_a_played_npc(self) -> None:
        response = self.api(self.account_of(self.ysmay)).post(
            "/api/action-requests/",
            {
                "scene": self.scene.pk,
                "initiator_persona": persona_of(self.ysmay).pk,
                "target_persona": persona_of(self.hobb).pk,
                "action_key": "persuade",
            },
            format="json",
        )
        self.assertIn(response.status_code, (status.HTTP_200_OK, status.HTTP_201_CREATED))
        self.assertEqual(response.json()["status"], "resolved")
        self.assertFalse(
            WeeklySocialEngagement.objects.filter(account=self.account_of(self.hobb)).exists()
        )

    def test_battle_counts_no_pc_opponent_for_a_played_npc(self) -> None:
        content = ensure_surrounded_content()
        battle = create_battle(name="The Lantern Riot")
        attackers = add_side(battle=battle, role=BattleSideRole.ATTACKER)
        defenders = add_side(battle=battle, role=BattleSideRole.DEFENDER)
        place = add_place(battle=battle, name="The Gates")
        isolated = enlist_participant(
            battle=battle,
            character_sheet=self.ysmay.sheet_data,
            side=attackers,
            place=place,
        )
        enlist_participant(
            battle=battle,
            character_sheet=self.hobb.sheet_data,
            side=defenders,
            place=place,
        )
        pool = select_surrounded_terminal_pool(battle=battle, participant=isolated)
        self.assertEqual(pool.name, POOL_SURROUNDED_TERMINAL_ENEMY)
        self.assertEqual(pool, content["pools"]["surrounded_terminal_enemy"])


class AnNpcActsOnAPc(JourneyCase):
    """Hobb is a major NPC a GM plays; Ysmay is a player character he acts on."""

    RESIST_ONLY_LINE = "You can resist this, but not refuse it."

    def setUp(self) -> None:
        super().setUp()
        self.room = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.hobb = self.make_player("Hobb", room=self.room)
        entry = self.hobb.sheet_data.roster_entry
        entry.move_to_roster(RosterFactory(roster_type=RosterType.NPC))
        self.scene = SceneFactory(room=self.room)
        check_type = CheckTypeFactory(name="Persuasion")
        self.deceive = ActionTemplateFactory(name="Deceive", check_type=check_type)
        self.romantic = SocialConsentCategoryFactory(key="romantic", name="Romantic")
        self.romantic.refusable_from_npcs = True
        self.romantic.save()
        self.flirt = ActionTemplateFactory(
            name="Flirt", check_type=check_type, consent_category=self.romantic
        )

    def _npc_acts(self, action_key: str) -> dict:
        response = self.api(self.account_of(self.hobb)).post(
            "/api/action-requests/",
            {
                "scene": self.scene.pk,
                "initiator_persona": persona_of(self.hobb).pk,
                "target_persona": persona_of(self.ysmay).pk,
                "action_key": action_key,
            },
            format="json",
        )
        self.assertIn(response.status_code, (status.HTTP_200_OK, status.HTTP_201_CREATED))
        return response.json()

    def _ysmay_responds(self, request_id: int, decision: str):
        return self.api(self.account_of(self.ysmay)).post(
            f"/api/action-requests/{request_id}/respond/",
            {"decision": decision},
            format="json",
        )

    def test_deny_is_refused_on_a_resist_only_request(self) -> None:
        body = self._npc_acts("deceive")
        self.assertEqual(body["status"], "pending")
        self.assertIs(body["resist_only"], True)
        response = self._ysmay_responds(body["id"], "deny")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()["detail"], self.RESIST_ONLY_LINE)
        told = self.telnet(self.ysmay, f"deny {body['id']}")
        self.assertIn(self.RESIST_ONLY_LINE, told)

    def test_a_romantic_action_still_asks(self) -> None:
        body = self._npc_acts("flirt")
        self.assertEqual(body["status"], "pending")
        self.assertIs(body["resist_only"], False)
        response = self._ysmay_responds(body["id"], "deny")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["status"], "denied")
