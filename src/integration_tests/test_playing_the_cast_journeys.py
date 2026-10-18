"""Journeys for playing the cast (#4418): a GM or Guide plays a major NPC in a scene."""

from __future__ import annotations

from rest_framework import status

from actions.factories import ActionTemplateFactory
from integration_tests.harness import JourneyCase
from world.battles.constants import BattleSideRole
from world.battles.resolution import select_surrounded_terminal_pool
from world.battles.services import add_place, add_side, create_battle, enlist_participant
from world.checks.factories import CheckTypeFactory
from world.checks.services import compute_check_rating
from world.checks.test_helpers import force_check_outcome
from world.consent.factories import SocialConsentCategoryFactory
from world.progression.models import WeeklySocialEngagement
from world.roster.factories import RosterFactory
from world.roster.models.choices import RosterType
from world.scenes.action_models import SceneActionRequest
from world.scenes.action_services import create_action_request
from world.scenes.factories import SceneFactory
from world.traits.factories import CheckOutcomeFactory
from world.traits.models import CheckOutcome
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
    NOT_YET_LINE = "That action can't be used by an NPC on a player character yet."

    def setUp(self) -> None:
        super().setUp()
        self.room = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.hobb = self.make_player("Hobb", room=self.room)
        entry = self.hobb.sheet_data.roster_entry
        entry.move_to_roster(RosterFactory(roster_type=RosterType.NPC))
        self.scene = SceneFactory(room=self.room)
        self.persuasion = CheckTypeFactory(name="Persuasion")
        self.insight = CheckTypeFactory(name="Insight")
        antagonism = SocialConsentCategoryFactory(key="antagonism", name="Antagonism")
        self.deceive = ActionTemplateFactory(
            name="Deceive",
            check_type=self.persuasion,
            resist_check_type=self.insight,
            consent_category=antagonism,
        )
        self.romantic = SocialConsentCategoryFactory(key="romantic", name="Romantic")
        self.romantic.refusable_from_npcs = True
        self.romantic.save()
        self.flirt = ActionTemplateFactory(
            name="Flirt",
            check_type=self.persuasion,
            resist_check_type=self.insight,
            consent_category=self.romantic,
        )

    def _npc_posts(self, action_key: str):
        return self.api(self.account_of(self.hobb)).post(
            "/api/action-requests/",
            {
                "scene": self.scene.pk,
                "initiator_persona": persona_of(self.hobb).pk,
                "target_persona": persona_of(self.ysmay).pk,
                "action_key": action_key,
            },
            format="json",
        )

    def _npc_acts(self, action_key: str) -> dict:
        response = self._npc_posts(action_key)
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

    def test_a_resist_only_extra_target_cannot_be_denied(self) -> None:
        wren = self.make_player("Wren", room=self.room)
        # No social action takes a group over the API yet, so the extra row is set up
        # through the service; the refusal is still read off the respond endpoint.
        action_request = create_action_request(
            scene=self.scene,
            initiator_persona=persona_of(self.hobb),
            target_persona=persona_of(self.ysmay),
            action_key="deceive",
            additional_target_personas=[persona_of(wren)],
        )
        request_id = action_request.pk
        denied = self.api(self.account_of(wren)).post(
            f"/api/action-requests/{request_id}/respond/",
            {"decision": "deny", "target_persona_id": persona_of(wren).pk},
            format="json",
        )
        self.assertEqual(denied.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(denied.json()["detail"], self.RESIST_ONLY_LINE)

    def test_a_pc_acting_on_a_pc_is_still_deniable(self) -> None:
        wren = self.make_player("Wren", room=self.room)
        response = self.api(self.account_of(wren)).post(
            "/api/action-requests/",
            {
                "scene": self.scene.pk,
                "initiator_persona": persona_of(wren).pk,
                "target_persona": persona_of(self.ysmay).pk,
                "action_key": "deceive",
            },
            format="json",
        )
        body = response.json()
        self.assertIs(body["resist_only"], False)
        denied = self._ysmay_responds(body["id"], "deny")
        self.assertEqual(denied.status_code, status.HTTP_200_OK)
        self.assertEqual(denied.json()["status"], "denied")

    def test_a_child_of_a_flagged_category_is_refusable(self) -> None:
        child = SocialConsentCategoryFactory(
            key="courtship", name="Courtship", parent=self.romantic
        )
        self.flirt.consent_category = child
        self.flirt.save()
        body = self._npc_acts("flirt")
        self.assertIs(body["resist_only"], False)
        denied = self._ysmay_responds(body["id"], "deny")
        self.assertEqual(denied.status_code, status.HTTP_200_OK)
        self.assertEqual(denied.json()["status"], "denied")

    def test_the_pc_rolls_to_see_through_the_lie(self) -> None:
        seen_through = CheckOutcomeFactory(name="Sees right through it", success_level=2)
        CheckOutcomeFactory(name="Caught in the lie", success_level=-2)
        body = self._npc_acts("deceive")
        self.assertEqual(body["status"], "pending")
        with force_check_outcome(seen_through) as capture:
            response = self.api(self.account_of(self.ysmay)).post(
                f"/api/action-requests/{body['id']}/respond/",
                {"decision": "accept", "resist_effort": "high"},
                format="json",
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["status"], "resolved")
        self.assertEqual(capture.check_type, self.insight)
        self.assertEqual(
            capture.target_difficulty, compute_check_rating(self.hobb, self.persuasion)
        )
        main = response.json()["result"]["action_resolution"]["main_result"]
        self.assertLess(CheckOutcome.objects.get(name=main["check_outcome"]).success_level, 0)
        self.assertEqual(main["check_outcome"], "Caught in the lie")

    def test_no_resist_check_refuses_before_any_row(self) -> None:
        self.deceive.resist_check_type = None
        self.deceive.save()
        response = self._npc_posts("deceive")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()["detail"], [self.NOT_YET_LINE])
        self.assertEqual(SceneActionRequest.objects.count(), 0)

    def test_untagged_template_refuses_npc_on_pc(self) -> None:
        ActionTemplateFactory(
            name="Seduce",
            check_type=self.persuasion,
            resist_check_type=self.insight,
            consent_category=None,
        )
        response = self._npc_posts("seduce")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()["detail"], [self.NOT_YET_LINE])
        self.assertEqual(SceneActionRequest.objects.count(), 0)
