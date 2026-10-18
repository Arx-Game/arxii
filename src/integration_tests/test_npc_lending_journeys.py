"""Journeys for lending a major NPC (#4418): a GM lends Captain Vael to a Guide for a scene."""

from __future__ import annotations

from functools import partial
from unittest.mock import Mock, patch
import uuid

import evennia
from evennia.server.serversession import ServerSession
from rest_framework import status

from actions.factories import ActionTemplateFactory
from evennia_extensions.models import RoomProfile
from integration_tests.harness import JourneyCase
from world.battles.constants import BattleOutcome
from world.battles.factories import BattleFactory
from world.battles.services import conclude_battle
from world.checks.factories import CheckTypeFactory
from world.events.constants import EventStatus
from world.events.factories import EventFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory, GuideProfileFactory, seed_default_gm_level_caps
from world.roster.constants import NPCLoanStatus
from world.roster.factories import NPCLoanFactory
from world.roster.models import NPCLoan, RosterEntry
from world.scenes.factories import SceneFactory, SceneParticipationFactory

MINE = "/api/roster/entries/mine/"
SELECT = "/api/roster/entries/select/"
SUBMIT_POSE = "/api/interactions/submit-pose/"
NO_ACCESS = "You don't have access to that character."


def persona_of(character):
    return character.sheet_data.primary_persona


class AGuidePlaysALentNpc(JourneyCase):
    """Ravenna GMs the siege and owns Captain Vael; Ilsa is a Guide; Ysmay is a PC."""

    def setUp(self) -> None:
        super().setUp()
        seed_default_gm_level_caps()
        self.room = self.make_room("Low Gate")
        self.ravenna = self.make_player("Ravenna", room=self.room)
        self.gm = self.account_of(self.ravenna)
        GMProfileFactory(account=self.gm, level=GMLevel.JUNIOR)
        self.ilsa = self.make_player("Ilsa", room=self.room)
        self.guide = self.account_of(self.ilsa)
        self.guide_profile = GuideProfileFactory(account=self.guide)
        self.ysmay = self.make_player("Ysmay", room=self.room)

        minted = self.web(
            self.ravenna, "mint_story_npc", name="Captain Vael", description="A grizzled officer."
        )
        self.assertTrue(minted.detail.success, minted.detail.message)
        self.entry = RosterEntry.objects.get(pk=minted.detail.data["roster_entry_id"])
        self.vael = self.entry.character_sheet.character
        self.vael.location = self.room
        self.vael.save()

        self.scene = SceneFactory(room=self.room, name="The Siege at Low Gate")
        SceneParticipationFactory(scene=self.scene, account=self.gm, is_gm=True, is_owner=True)

    # -- helpers ---------------------------------------------------------------

    def _offer(self, guide_account=None):
        guide_account = guide_account or self.guide
        return self.web(
            self.ravenna,
            "offer_npc",
            roster_entry_id=self.entry.pk,
            guide_account_id=guide_account.pk,
        )

    def _lend(self) -> int:
        offered = self._offer()
        self.assertTrue(offered.detail.success, offered.detail.message)
        loan_id = offered.detail.data["loan_id"]
        accepted = self.web(self.ilsa, "answer_npc_loan", loan_id=loan_id, accept=True)
        self.assertTrue(accepted.detail.success, accepted.detail.message)
        return loan_id

    def _mine_names(self, account) -> list[str]:
        response = self.api(account).get(MINE)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return [row["name"] for row in response.json()]

    def _pose_as_vael(self, account):
        return self.api(account).post(
            SUBMIT_POSE,
            {
                "persona_id": persona_of(self.vael).pk,
                "scene_id": self.scene.pk,
                "content": "Hold the gate!",
                "client_request_id": str(uuid.uuid4()),
            },
            format="json",
        )

    # -- journeys --------------------------------------------------------------

    def test_offer_accept_play_and_scene_end_returns_it(self) -> None:
        self._lend()

        response = self.api(self.guide).get(MINE)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rows = {row["name"]: row for row in response.json()}
        self.assertIn("Captain Vael", rows)
        self.assertEqual(rows["Captain Vael"]["loan"]["scene_title"], "The Siege at Low Gate")
        self.assertIsNone(rows["Ilsa"]["loan"])

        posed = self._pose_as_vael(self.guide)
        self.assertIn(posed.status_code, (status.HTTP_200_OK, status.HTTP_201_CREATED), posed.data)

        ActionTemplateFactory(name="Persuade", check_type=CheckTypeFactory(name="Persuasion"))
        persuaded = self.api(self.account_of(self.ysmay)).post(
            "/api/action-requests/",
            {
                "scene": self.scene.pk,
                "initiator_persona": persona_of(self.ysmay).pk,
                "target_persona": persona_of(self.vael).pk,
                "action_key": "persuade",
            },
            format="json",
        )
        self.assertIn(persuaded.status_code, (status.HTTP_200_OK, status.HTTP_201_CREATED))
        self.assertEqual(persuaded.json()["status"], "resolved")

        finished = self.web(self.ravenna, "finish_scene")
        self.assertTrue(finished.detail.success, finished.detail.message)
        self.assertNotIn("Captain Vael", self._mine_names(self.guide))
        self.assertIn("Captain Vael", self._mine_names(self.gm))

    def test_completing_an_event_returns_the_lent_npc(self) -> None:
        event = EventFactory(
            status=EventStatus.ACTIVE, location=RoomProfile.objects.get(objectdb=self.room)
        )
        self.scene.event = event
        self.scene.is_active = True
        self.scene.save()
        self._lend()
        self.assertIn("Captain Vael", self._mine_names(self.guide))

        said = self.telnet(self.ravenna, f"event complete {event.pk}")
        self.assertIn("is complete", said)
        self.assertNotIn("Captain Vael", self._mine_names(self.guide))
        self.assertIn("Captain Vael", self._mine_names(self.gm))

    def test_concluding_a_battle_returns_the_lent_npc(self) -> None:
        battle = BattleFactory()
        loan = NPCLoanFactory(
            roster_entry=self.entry,
            borrower=self.guide,
            offered_by=self.gm,
            scene=battle.scene,
            status=NPCLoanStatus.ACTIVE,
        )

        conclude_battle(battle=battle, outcome=BattleOutcome.ATTACKER_DECISIVE)

        loan.refresh_from_db()
        self.assertNotEqual(loan.status, NPCLoanStatus.ACTIVE)
        self.assertNotIn("Captain Vael", self._mine_names(self.guide))
        self.assertIn("Captain Vael", self._mine_names(self.gm))

    def test_owner_loses_the_npc_while_it_is_lent(self) -> None:
        self.assertIn("Captain Vael", self._mine_names(self.gm))
        self.assertIs(self.gm.can_puppet_character(self.vael)[0], True)

        self._lend()

        self.assertNotIn("Captain Vael", self._mine_names(self.gm))
        allowed, reason = self.gm.can_puppet_character(self.vael)
        self.assertIs(allowed, False)
        self.assertEqual(reason, NO_ACCESS)
        self.assertNotIn(persona_of(self.vael).pk, self.gm.cached_persona_ids)
        refused = self._pose_as_vael(self.gm)
        self.assertEqual(refused.status_code, status.HTTP_400_BAD_REQUEST)

    def test_take_back_unpuppets_and_forgets_personas(self) -> None:
        loan_id = self._lend()
        self.assertIn(persona_of(self.vael).pk, self.guide.cached_persona_ids)
        self.assertIs(self.guide.can_puppet_character(self.vael)[0], True)

        taken = self.web(self.ravenna, "take_back_npc", loan_id=loan_id)
        self.assertTrue(taken.detail.success, taken.detail.message)

        self.assertNotIn(persona_of(self.vael).pk, self.guide.cached_persona_ids)
        self.assertIs(self.guide.can_puppet_character(self.vael)[0], False)
        refused = self._pose_as_vael(self.guide)
        self.assertEqual(refused.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIs(self.gm.can_puppet_character(self.vael)[0], True)
        self.assertEqual(NPCLoan.objects.get(pk=loan_id).status, "ended")

    def test_a_guide_playing_a_lent_npc_has_no_gm_powers(self) -> None:
        loan_id = self._lend()
        self.assertEqual(self.vael.active_account, self.guide)

        # Acting as Vael, Ilsa is Ilsa: not the scene's owner, not a GM.
        finish = self.web(self.vael, "finish_scene")
        self.assertFalse(finish.detail.success)
        self.assertEqual(
            finish.detail.message, "Only the scene's GM or an owner can finish the scene."
        )
        mint = self.web(self.vael, "mint_story_npc", name="Corporal Brann", description="Young.")
        self.assertFalse(mint.detail.success)
        self.assertEqual(mint.detail.message, "GM trust required.")
        self.assertFalse(
            RosterEntry.objects.filter(character_sheet__character__db_key="Corporal Brann").exists()
        )
        self.scene.refresh_from_db()
        self.assertTrue(self.scene.is_active)

        taken = self.web(self.ravenna, "take_back_npc", loan_id=loan_id)
        self.assertTrue(taken.detail.success, taken.detail.message)
        self.assertEqual(self.vael.active_account, self.gm)

        # The owner, on her own character, still runs her scene.
        finished = self.web(self.ravenna, "finish_scene")
        self.assertTrue(finished.detail.success, finished.detail.message)

    def test_a_saved_selection_does_not_outlive_who_plays_the_npc(self) -> None:
        apparent = "/api/forms/character-forms/apparent/"
        # Ravenna had Vael taken up on the website; lending him drops that selection.
        ravenna_web = self.api(self.gm)
        self.assertEqual(
            ravenna_web.post(SELECT, {"entry_id": self.entry.pk}, format="json").status_code,
            status.HTTP_200_OK,
        )
        loan_id = self._lend()
        self.assertIsNone(self.gm.player_data.selected_entry_id)

        # Ilsa takes Vael up; a page that reads her selection now acts as Vael.
        ilsa_web = self.api(self.guide)
        selected = ilsa_web.post(SELECT, {"entry_id": self.entry.pk}, format="json")
        self.assertEqual(selected.status_code, status.HTTP_200_OK, selected.data)
        self.assertNotEqual(ilsa_web.get(apparent).status_code, status.HTTP_400_BAD_REQUEST)

        taken = self.web(self.ravenna, "take_back_npc", loan_id=loan_id)
        self.assertTrue(taken.detail.success, taken.detail.message)
        self.assertIsNone(self.guide.player_data.selected_entry_id)
        after = ilsa_web.get(apparent)
        self.assertEqual(after.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(after.json()["detail"], "No active character")

    def test_accept_takes_a_string_yes(self) -> None:
        offered = self._offer()
        loan_id = offered.detail.data["loan_id"]
        accepted = self.web(self.ilsa, "answer_npc_loan", loan_id=loan_id, accept="true")
        self.assertTrue(accepted.detail.success, accepted.detail.message)
        self.assertEqual(NPCLoan.objects.get(pk=loan_id).status, "active")

    def test_only_a_guide_may_accept(self) -> None:
        # Ysmay is no Guide: she cannot be offered the NPC.
        refused_offer = self._offer(self.account_of(self.ysmay))
        self.assertFalse(refused_offer.detail.success)
        self.assertFalse(NPCLoan.objects.filter(borrower=self.account_of(self.ysmay)).exists())

        offered = self._offer()
        self.assertTrue(offered.detail.success, offered.detail.message)
        loan_id = offered.detail.data["loan_id"]

        # Nor can she take up an offer made to Ilsa.
        stolen = self.web(self.ysmay, "answer_npc_loan", loan_id=loan_id, accept=True)
        self.assertFalse(stolen.detail.success)

        # And once Ilsa is no longer a Guide, she cannot accept it either.
        self.guide_profile.is_active = False
        self.guide_profile.save()
        lapsed = self.web(self.ilsa, "answer_npc_loan", loan_id=loan_id, accept=True)
        self.assertFalse(lapsed.detail.success)

        self.assertEqual(NPCLoan.objects.get(pk=loan_id).status, "offered")
        self.assertNotIn("Captain Vael", self._mine_names(self.guide))
        self.assertIn("Captain Vael", self._mine_names(self.gm))

    def _signed_in(self, character, sessid: int) -> ServerSession:
        """A telnet session signed in as ``character``'s account.

        ``@ic`` switches the session the line came from, so the line has to arrive on
        one: the session is passed into ``execute_cmd`` for every line typed.
        """
        handler = evennia.SESSION_HANDLER
        for name in ("data_out", "disconnect"):
            patcher = patch.object(handler, name, Mock())
            patcher.start()
            self.addCleanup(patcher.stop)
        dummy = ServerSession()
        dummy.init_session("telnet", ("localhost", "testmode"), handler)
        dummy.sessid = sessid
        handler.portal_connect(dummy.get_sync_data())
        session = handler.session_from_sessid(sessid)
        self.addCleanup(handler.pop, sessid, None)
        account = self.account_of(character)
        handler.login(session, account, testmode=True)
        character.execute_cmd = partial(type(character).execute_cmd, character, session=session)
        self.addCleanup(character.__dict__.pop, "execute_cmd", None)
        return session

    def test_telnet_switch_onto_a_lent_npc(self) -> None:
        # Vael was minted before #4418: only a developer could puppet him. Lending fixes it.
        self.vael.locks.add("puppet:pperm(Developer)")
        self._lend()
        session = self._signed_in(self.ilsa, sessid=4418)
        told = self.telnet(self.ilsa, "@ic Captain Vael")
        self.assertNotIn(NO_ACCESS, told)
        self.assertIn("Now controlling Captain Vael.", told)
        self.assertIs(session.puppet, self.vael)

    def test_the_owner_plays_a_freshly_minted_npc(self) -> None:
        session = self._signed_in(self.ravenna, sessid=4419)
        told = self.telnet(self.ravenna, "@ic Captain Vael")
        self.assertIn("Now controlling Captain Vael.", told)
        self.assertIs(session.puppet, self.vael)

    def test_a_scene_ends_with_an_unplayed_npc_in_the_room(self) -> None:
        self.assertIsNone(self.vael.account)
        finished = self.web(self.ravenna, "finish_scene")
        self.assertTrue(finished.detail.success, finished.detail.message)
        self.scene.refresh_from_db()
        self.assertFalse(self.scene.is_active)

    def test_a_loan_saved_outside_the_services_still_shows(self) -> None:
        # Staff can mark a loan active from the admin; the cached lists must follow.
        self.assertNotIn(self.vael, self.guide.get_available_characters())
        self.assertNotIn(self.vael, self.guide.player_data.get_available_characters())
        NPCLoanFactory(
            roster_entry=self.entry, borrower=self.guide, offered_by=self.gm, status="active"
        )
        self.assertIn(self.vael, self.guide.get_available_characters())
        self.assertIn(self.vael, self.guide.player_data.get_available_characters())
        self.assertNotIn(self.vael, self.gm.player_data.get_available_characters())
