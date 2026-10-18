"""Journeys for playing the cast (#4418): a GM or Guide plays a major NPC in a scene."""

from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from evennia.utils.idmapper import models as idmapper_models
from rest_framework import status

from actions.constants import ActionCategory, ActionTargetType
from actions.factories import ActionTemplateFactory
from integration_tests.harness import JourneyCase
from world.battles.constants import BattleSideRole
from world.battles.resolution import select_surrounded_terminal_pool
from world.battles.services import add_place, add_side, create_battle, enlist_participant
from world.checks.factories import CheckTypeFactory
from world.checks.services import compute_check_rating
from world.checks.test_helpers import force_check_outcome
from world.combat.constants import OpponentTier
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    ThreatPoolFactory,
)
from world.combat.models import CombatOpponent
from world.consent.factories import SocialConsentCategoryFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory, GuideProfileFactory, seed_default_gm_level_caps
from world.progression.models import WeeklySocialEngagement
from world.roster.factories import RosterFactory
from world.roster.models import RosterEntry
from world.roster.models.choices import RosterType
from world.scenes.action_models import SceneActionRequest
from world.scenes.action_services import create_action_request
from world.scenes.constants import RoundStatus
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.scenes.models import Interaction
from world.traits.factories import CheckOutcomeFactory, CheckSystemSetupFactory
from world.traits.models import CheckOutcome, ResultChart
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
            category=ActionCategory.SOCIAL,
            target_type=ActionTargetType.SINGLE,
            check_type=self.persuasion,
            resist_check_type=self.insight,
            consent_category=antagonism,
        )
        self.romantic = SocialConsentCategoryFactory(key="romantic", name="Romantic")
        self.romantic.refusable_from_npcs = True
        self.romantic.save()
        self.flirt = ActionTemplateFactory(
            name="Flirt",
            category=ActionCategory.SOCIAL,
            target_type=ActionTargetType.SINGLE,
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
        self.assertEqual(body["resist_check_name"], "Insight")
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

    def _untagged_seduce(self) -> None:
        ActionTemplateFactory(
            name="Seduce",
            category=ActionCategory.SOCIAL,
            target_type=ActionTargetType.SINGLE,
            check_type=self.persuasion,
            resist_check_type=self.insight,
            consent_category=None,
        )

    def test_untagged_template_refuses_npc_on_pc(self) -> None:
        self._untagged_seduce()
        response = self._npc_posts("seduce")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()["detail"], [self.NOT_YET_LINE])
        self.assertEqual(SceneActionRequest.objects.count(), 0)

    def test_untagged_template_refuses_a_pc_extra_target(self) -> None:
        self._untagged_seduce()
        tam = self.make_player("Tam", room=self.room)
        tam.sheet_data.roster_entry.move_to_roster(RosterFactory(roster_type=RosterType.NPC))
        # No social action takes a group over the API yet, so the group is asked for
        # through the service the API calls.
        with self.assertRaises(ValidationError) as refused:
            create_action_request(
                scene=self.scene,
                initiator_persona=persona_of(self.hobb),
                target_persona=persona_of(tam),
                action_key="seduce",
                additional_target_personas=[persona_of(self.ysmay)],
            )
        self.assertEqual(refused.exception.messages, [self.NOT_YET_LINE])
        self.assertEqual(SceneActionRequest.objects.count(), 0)

    def test_a_template_that_is_not_contested_keeps_todays_path(self) -> None:
        ActionTemplateFactory(
            name="Intimidate",
            category=ActionCategory.PHYSICAL,
            target_type=ActionTargetType.SINGLE,
            check_type=self.persuasion,
        )
        body = self._npc_acts("intimidate")
        self.assertEqual(body["status"], "pending")
        self.assertIs(body["resist_only"], False)
        denied = self._ysmay_responds(body["id"], "deny")
        self.assertEqual(denied.status_code, status.HTTP_200_OK)
        self.assertEqual(denied.json()["status"], "denied")

    def test_an_untagged_group_social_template_is_deniable(self) -> None:
        ActionTemplateFactory(
            name="Intimidate",
            category=ActionCategory.SOCIAL,
            target_type=ActionTargetType.FILTERED_GROUP,
            check_type=self.persuasion,
        )
        body = self._npc_acts("intimidate")
        self.assertEqual(body["status"], "pending")
        self.assertIs(body["resist_only"], False)
        denied = self._ysmay_responds(body["id"], "deny")
        self.assertEqual(denied.status_code, status.HTTP_200_OK)
        self.assertEqual(denied.json()["status"], "denied")

    def test_the_wheel_spins_the_pcs_own_roll(self) -> None:
        setup = CheckSystemSetupFactory.create()
        ResultChart.clear_cache()
        self.addCleanup(ResultChart.clear_cache)
        body = self._npc_acts("deceive")
        self.watch(self.ysmay)
        with (
            self.captureOnCommitCallbacks(execute=True),
            force_check_outcome(setup["outcomes"]["success"]),
        ):
            response = self.api(self.account_of(self.ysmay)).post(
                f"/api/action-requests/{body['id']}/respond/",
                {"decision": "accept", "resist_effort": "high"},
                format="json",
            )
        main = response.json()["result"]["action_resolution"]["main_result"]
        self.assertEqual(main["check_outcome"], "Failure")
        wheels = [
            kwargs["roulette_result"][1]
            for _args, kwargs in self.mailbox(self.ysmay).calls
            if "roulette_result" in kwargs
        ]
        self.assertTrue(wheels)
        selected = [face for face in wheels[0]["consequences"] if face["is_selected"]]
        self.assertEqual([face["tier_name"] for face in selected], ["Success"])


CAST_LIST = "/api/scenes/{}/cast-list/"
SUBMIT_POSE = "/api/interactions/submit-pose/"
GUIDES = "/api/gm/guides/"


class TheGmSeesTheCast(JourneyCase):
    """Ravenna GMs the siege at Low Gate; Wren's player is the Guide staff call "Ilsa";
    Ysmay is a player there."""

    def setUp(self) -> None:
        super().setUp()
        seed_default_gm_level_caps()
        self.room = self.make_room("Low Gate")
        self.ravenna = self.make_player("Ravenna", room=self.room)
        self.gm = self.account_of(self.ravenna)
        GMProfileFactory(account=self.gm, level=GMLevel.JUNIOR)
        self.wren = self.make_player("Wren", room=self.room)
        self.guide = self.account_of(self.wren)
        GuideProfileFactory(account=self.guide, display_name="Ilsa")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.scene = SceneFactory(room=self.room, name="The Siege at Low Gate")
        SceneParticipationFactory(scene=self.scene, account=self.gm, is_gm=True, is_owner=True)
        self.encounter = CombatEncounterFactory(scene=self.scene, room=self.room)
        self.pool = ThreatPoolFactory(name="Low Gate watch")
        self.guards = self._mooks(self.encounter, self.pool, 8)

    # -- helpers ---------------------------------------------------------------

    @staticmethod
    def _mooks(encounter, pool, count: int) -> list:
        return [
            CombatOpponentFactory(
                encounter=encounter,
                tier=OpponentTier.MOOK,
                threat_pool=pool,
                name=f"{pool.name} {number}",
            )
            for number in range(count)
        ]

    def _mint(self, name: str):
        minted = self.web(self.ravenna, "mint_story_npc", name=name, description="An officer.")
        self.assertTrue(minted.detail.success, minted.detail.message)
        entry = RosterEntry.objects.get(pk=minted.detail.data["roster_entry_id"])
        character = entry.character_sheet.character
        character.location = self.room
        character.save()
        return entry

    def _voice(self, opponents, name: str):
        return self.web(
            self.ravenna,
            "voice_crowd",
            opponent_ids=[opponent.pk for opponent in opponents],
            name=name,
        )

    def _lend(self, entry_id: int) -> None:
        offered = self.web(
            self.ravenna, "offer_npc", roster_entry_id=entry_id, guide_account_id=self.guide.pk
        )
        self.assertTrue(offered.detail.success, offered.detail.message)
        accepted = self.web(
            self.wren, "answer_npc_loan", loan_id=offered.detail.data["loan_id"], accept=True
        )
        self.assertTrue(accepted.detail.success, accepted.detail.message)

    def _cast_list(self):
        response = self.api(self.gm).get(CAST_LIST.format(self.scene.pk))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response

    # -- journeys --------------------------------------------------------------

    def test_cast_lists_npcs_and_crowds(self) -> None:
        vael = self._mint("Captain Vael")
        CombatOpponentFactory(
            encounter=self.encounter,
            tier=OpponentTier.SWARM,
            name="Besieger skirmishers",
            swarm_count=30,
            max_swarm_count=30,
            threat_pool=ThreatPoolFactory(name="Besiegers"),
        )
        # An encounter that has ended no longer puts anyone in the cast.
        finished = CombatEncounterFactory(
            scene=self.scene, room=self.room, status=RoundStatus.COMPLETED
        )
        CombatOpponentFactory(encounter=finished, name="Routed sapper")

        response = self._cast_list()

        rows = response.json()
        self.assertEqual(
            [row["name"] for row in rows],
            ["Captain Vael", "Low Gate watch", "Besieger skirmishers"],
        )
        self.assertEqual([row["count"] for row in rows], [None, 8, 30])
        self.assertEqual([row["kind"] for row in rows], ["npc", "crowd", "crowd"])
        self.assertEqual(rows[0]["roster_entry_id"], vael.pk)
        self.assertEqual(rows[0]["opponent_ids"], [])
        self.assertEqual(sorted(rows[1]["opponent_ids"]), sorted(g.pk for g in self.guards))
        # Ravenna has no GM character: she shows as her role, never as her PC.
        self.assertEqual(rows[0]["played_by"], "GM")
        self.assertEqual(rows[0]["description"], "An officer.")
        body = response.content.decode()
        self.assertNotIn(self.gm.username, body)
        self.assertNotIn("Ravenna", body)

        refused = self.api(self.account_of(self.ysmay)).get(CAST_LIST.format(self.scene.pk))
        self.assertEqual(refused.status_code, status.HTTP_404_NOT_FOUND)

    def test_a_crowd_poses_under_its_own_name(self) -> None:
        # The GM voices the crowd with exactly the ids its cast list row carries.
        (crowd,) = self._cast_list().json()
        self.assertEqual(len(crowd["opponent_ids"]), 8)
        voiced = self.web(
            self.ravenna, "voice_crowd", opponent_ids=crowd["opponent_ids"], name="Gate guards"
        )
        self.assertTrue(voiced.detail.success, voiced.detail.message)
        persona_id = voiced.detail.data["persona_id"]
        self._lend(voiced.detail.data["roster_entry_id"])

        response = self._cast_list()
        rows = response.json()
        self.assertEqual([row["name"] for row in rows], ["Gate guards"])
        self.assertEqual(rows[0]["count"], 8)
        # The Guide shows by the name staff gave her, never by her own character.
        self.assertEqual(rows[0]["played_by"], "Ilsa")
        self.assertNotIn("Wren", response.content.decode())
        self.assertEqual(rows[0]["loan_status"], "active")

        posed = self.api(self.guide).post(
            SUBMIT_POSE,
            {
                "persona_id": persona_id,
                "scene_id": self.scene.pk,
                "content": "Shields up! Hold the line!",
                "client_request_id": str(uuid.uuid4()),
            },
            format="json",
        )
        self.assertIn(posed.status_code, (status.HTTP_200_OK, status.HTTP_201_CREATED), posed.data)
        interaction = Interaction.objects.filter(content="Shields up! Hold the line!").get()
        self.assertEqual(interaction.persona.name, "Gate guards")
        self.assertEqual(CombatOpponent.objects.filter(persona__isnull=False).count(), 0)

    def test_a_finished_fight_returns_its_voice_to_the_npcs(self) -> None:
        voiced = self._voice(self.guards, "Gate guards")
        self.assertTrue(voiced.detail.success, voiced.detail.message)

        self.encounter.status = RoundStatus.COMPLETED
        self.encounter.save()

        rows = self._cast_list().json()
        self.assertEqual([(row["name"], row["kind"]) for row in rows], [("Gate guards", "npc")])
        self.assertIsNone(rows[0]["count"])

    def test_crowd_voices_do_not_count_against_the_cap(self) -> None:
        # A junior GM may keep two story NPCs; voices are not among them.
        self._mint("Captain Vael")
        self.assertTrue(self._voice(self.guards, "Gate guards").detail.success)
        self._mint("Corporal Brann")
        archers = self._mooks(self.encounter, ThreatPoolFactory(name="Wall archers"), 3)
        voiced = self._voice(archers, "Wall archers")
        self.assertTrue(voiced.detail.success, voiced.detail.message)

        refused = self.web(self.ravenna, "mint_story_npc", name="Sergeant Holt", description="")
        self.assertFalse(refused.detail.success)
        self.assertFalse(
            RosterEntry.objects.filter(character_sheet__character__db_key="Sergeant Holt").exists()
        )

    def test_a_voice_is_refused_for_rows_that_are_not_one_crowd(self) -> None:
        other = CombatEncounterFactory(scene=self.scene, room=self.room)
        stray = CombatOpponentFactory(encounter=other, threat_pool=self.pool)
        split = self._voice([self.guards[0], stray], "Split guards")
        self.assertFalse(split.detail.success)

        elsewhere = CombatOpponentFactory()  # an encounter in another scene and room
        foreign = self._voice([elsewhere], "Distant guards")
        self.assertFalse(foreign.detail.success)
        self.assertIsNone(CombatOpponent.objects.get(pk=elsewhere.pk).voice_persona_id)

        self.assertTrue(self._voice(self.guards, "Gate guards").detail.success)
        again = self._voice(self.guards[:2], "Second voice")
        self.assertFalse(again.detail.success)
        self.assertFalse(
            RosterEntry.objects.filter(
                character_sheet__character__db_key__in=[
                    "Split guards",
                    "Distant guards",
                    "Second voice",
                ]
            ).exists()
        )
        voices = set(
            CombatOpponent.objects.filter(pk__in=[g.pk for g in self.guards]).values_list(
                "voice_persona__name", flat=True
            )
        )
        self.assertEqual(voices, {"Gate guards"})

    def test_cast_list_queries_do_not_grow_with_its_rows(self) -> None:
        self._mint("Captain Vael")
        voiced = self._voice(self.guards, "Gate guards")
        self._lend(voiced.detail.data["roster_entry_id"])
        idmapper_models.flush_cache()  # read the rows as a fresh server process would
        with CaptureQueriesContext(connection) as small:
            self._cast_list()

        self._mint("Corporal Brann")
        archers = self._mooks(self.encounter, ThreatPoolFactory(name="Wall archers"), 3)
        voiced = self._voice(archers, "Wall archers")
        self._lend(voiced.detail.data["roster_entry_id"])
        self._mooks(self.encounter, ThreatPoolFactory(name="Sappers"), 4)
        CombatOpponentFactory(
            encounter=self.encounter, tier=OpponentTier.SWARM, name="Rabble", swarm_count=12
        )
        idmapper_models.flush_cache()  # read the rows as a fresh server process would
        with CaptureQueriesContext(connection) as large:
            rows = self._cast_list().json()

        self.assertEqual(len(rows), 6)
        self.assertEqual(len(large.captured_queries), len(small.captured_queries))

    def test_a_gm_picks_a_guide_by_display_name(self) -> None:
        response = self.api(self.gm).get(GUIDES)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(
            response.json()["results"], [{"account_id": self.guide.pk, "display_name": "Ilsa"}]
        )
        self.assertNotIn(self.guide.username, response.content.decode())

        refused = self.api(self.account_of(self.ysmay)).get(GUIDES)
        self.assertEqual(refused.status_code, status.HTTP_403_FORBIDDEN)
