"""Journeys for lending a major NPC (#4418): a GM lends Captain Vael to a Guide for a scene."""

from __future__ import annotations

from functools import partial
from unittest.mock import Mock, patch
import uuid

from django.utils import timezone
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
from world.roster.services.staff_characters import ensure_playable_lock
from world.scenes.constants import InteractionMode
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.scenes.models import Interaction, Scene, SceneParticipation

MINE = "/api/roster/entries/mine/"
SELECT = "/api/roster/entries/select/"
SUBMIT_POSE = "/api/interactions/submit-pose/"
NO_ACCESS = "You don't have access to that character."


def _text_options(text) -> dict:
    """The options dict of an outgoing ``text`` frame (Evennia's ``(text, {opts})``)."""
    if isinstance(text, tuple) and len(text) > 1 and isinstance(text[1], dict):
        return text[1]
    return {}


def _text_body(text) -> str:
    """The words of an outgoing ``text`` frame."""
    return text[0] if isinstance(text, tuple) else str(text)


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

    def test_a_lent_npc_stays_in_the_scene_when_its_player_lets_go(self) -> None:
        # The ruling (#4418, bug 10): an unplayed story NPC still stands in the scene.
        loan_id = self._lend()
        session = self._signed_in(self.ilsa, sessid=4420)
        self.assertIn("Now controlling Captain Vael.", self.telnet(self.ilsa, "@ic Captain Vael"))
        self.assertIs(session.puppet, self.vael)

        taken = self.web(self.ravenna, "take_back_npc", loan_id=loan_id)
        self.assertTrue(taken.detail.success, taken.detail.message)
        self.assertIsNot(session.puppet, self.vael)
        self.assertEqual(self.vael.location, self.room)
        cast = self.api(self.gm).get(f"/api/scenes/{self.scene.pk}/cast-list/")
        self.assertEqual(cast.status_code, status.HTTP_200_OK, cast.data)
        self.assertIn("Captain Vael", [row["name"] for row in cast.json()])

        # Taken up again later, Vael is where he stood, not wherever he was before.
        self.vael.db.prelogout_location = self.make_room("Somewhere Stale")
        owner_session = self._signed_in(self.ravenna, sessid=4421)
        self.assertIn(
            "Now controlling Captain Vael.", self.telnet(self.ravenna, "@ic Captain Vael")
        )
        self.assertIs(owner_session.puppet, self.vael)
        self.assertEqual(self.vael.location, self.room)

    def test_a_gm_who_started_the_scene_may_offer_an_npc_for_it(self) -> None:
        # #4418 bug 9: Start Scene makes Ravenna an owner, not the scene's GM.
        self.scene.is_active = False
        self.scene.save()
        tavern = self.make_room("The Lantern")
        self.ravenna.move_to(tavern, quiet=True)
        self.vael.move_to(tavern, quiet=True)
        started = self.web(self.ravenna, "start_scene", name="A Night at the Lantern")
        self.assertTrue(started.detail.success, started.detail.message)
        scene = Scene.objects.get(name="A Night at the Lantern")
        self.assertFalse(scene.is_gm(self.gm))

        offered = self.web(
            self.ravenna,
            "offer_npc",
            roster_entry_id=self.entry.pk,
            guide_account_id=self.guide.pk,
            scene_id=scene.pk,
        )
        self.assertTrue(offered.detail.success, offered.detail.message)
        self.assertEqual(NPCLoan.objects.get(pk=offered.detail.data["loan_id"]).scene, scene)

    def test_whoever_plays_the_npc_is_recorded_as_writing_its_lines(self) -> None:
        # #4418 bug 3: a borrower's lines were pinned to the NPC's owner, so the
        # Guide's whisper as Vael was a private line of Ravenna's.
        loan_id = self._lend()
        posed = self._pose_as_vael(self.guide)
        self.assertIn(posed.status_code, (status.HTTP_200_OK, status.HTTP_201_CREATED), posed.data)
        self.telnet(self.vael, "whisper Ysmay=The gate opens at midnight.")

        vael_lines = Interaction.objects.filter(persona=persona_of(self.vael))
        pose = vael_lines.get(mode=InteractionMode.POSE)
        whisper = vael_lines.get(mode=InteractionMode.WHISPER)
        self.assertEqual(pose.writer_account_id, self.guide.pk)
        self.assertEqual(whisper.writer_account_id, self.guide.pk)
        self.assertEqual(
            list(whisper.receivers.values_list("account_id", flat=True)),
            [self.account_of(self.ysmay).pk],
        )

        taken = self.web(self.ravenna, "take_back_npc", loan_id=loan_id)
        self.assertTrue(taken.detail.success, taken.detail.message)
        self._pose_as_vael(self.gm)
        latest = vael_lines.filter(mode=InteractionMode.POSE).order_by("-pk").first()
        self.assertNotEqual(latest.pk, pose.pk)
        self.assertEqual(latest.writer_account_id, self.gm.pk)
        # The Guide's own whisper stays theirs to read once the loan is over.
        self.assertIn(whisper, Interaction.objects.visible_to(self.guide))

    def test_a_whisper_to_a_lent_npc_reaches_its_borrower(self) -> None:
        self._lend()
        lantern = self.make_room("The Lantern")
        elsewhere = SceneFactory(room=lantern, name="Elsewhere")
        self.assertFalse(
            SceneParticipation.objects.filter(scene=self.scene, account=self.guide).exists()
        )

        self.telnet(self.ysmay, "whisper Captain Vael=Let me through.")
        whisper = Interaction.objects.get(mode=InteractionMode.WHISPER)
        self.assertEqual(
            list(whisper.receivers.values_list("account_id", flat=True)), [self.guide.pk]
        )

        # The Guide takes part in the scene they posed in as Vael, and only that one.
        self._pose_as_vael(self.guide)
        joined = SceneParticipation.objects.filter(account=self.guide)
        self.assertEqual(list(joined.values_list("scene_id", flat=True)), [self.scene.pk])
        self.assertFalse(joined.filter(scene=elsewhere).exists())

    def _leave_the_gate_to(self, *characters) -> None:
        lantern = self.make_room("The Lantern")
        for character in characters:
            character.move_to(lantern, quiet=True)

    def test_the_scene_ends_when_only_an_unplayed_npc_is_left(self) -> None:
        # Round 2: Vael stays in the room unplayed, and must not hold the scene open.
        loan_id = self._lend()
        self._leave_the_gate_to(self.ilsa, self.ysmay, self.ravenna)

        self.scene.refresh_from_db()
        self.assertFalse(self.scene.is_active)
        self.assertEqual(NPCLoan.objects.get(pk=loan_id).status, NPCLoanStatus.ENDED)
        self.assertEqual(self.vael.location, self.room)

    def test_the_scene_ends_when_the_last_player_was_playing_an_npc(self) -> None:
        # Round 3: Ilsa, playing Vael, is the last player in Low Gate and disconnects.
        loan_id = self._lend()
        self._leave_the_gate_to(self.ilsa, self.ysmay)
        session = self._signed_in(self.ilsa, sessid=4424)
        self.assertIn("Now controlling Captain Vael.", self.telnet(self.ilsa, "@ic Captain Vael"))
        self._leave_the_gate_to(self.ravenna)
        self.scene.refresh_from_db()
        self.assertTrue(self.scene.is_active)

        session.account.unpuppet_object(session)

        self.scene.refresh_from_db()
        self.assertFalse(self.scene.is_active)
        self.assertEqual(NPCLoan.objects.get(pk=loan_id).status, NPCLoanStatus.ENDED)
        self.assertEqual(self.vael.location, self.room)

    def test_a_played_npc_keeps_the_scene_open(self) -> None:
        self._lend()
        self._leave_the_gate_to(self.ilsa, self.ysmay)
        session = self._signed_in(self.ilsa, sessid=4423)
        self.assertIn("Now controlling Captain Vael.", self.telnet(self.ilsa, "@ic Captain Vael"))
        self.assertIs(session.puppet, self.vael)

        self._leave_the_gate_to(self.ravenna)
        self.scene.refresh_from_db()
        self.assertTrue(self.scene.is_active)

    def _web_signed_in(
        self, character, sessid: int, *, puppet, protocol: str = "websocket"
    ) -> ServerSession:
        """A session of ``character``'s account puppeting ``puppet``, by default a
        browser's: "websocket" is the key Evennia's portal gives a live one."""
        handler = evennia.SESSION_HANDLER
        dummy = ServerSession()
        dummy.init_session(protocol, ("localhost", "testmode"), handler)
        dummy.sessid = sessid
        handler.portal_connect(dummy.get_sync_data())
        session = handler.session_from_sessid(sessid)
        self.addCleanup(handler.pop, sessid, None)
        account = self.account_of(character)
        handler.login(session, account, testmode=True)
        account.puppet_object(session, puppet)
        self.assertIs(session.puppet, puppet)
        return session

    def test_a_web_pose_reaches_each_web_session_once(self) -> None:
        # Bug E: a pose sent from the web composer arrived on every web session in
        # the room twice, as the Interaction and as an untagged text line the web
        # client shows as a note. The lent NPC's tab and a PC's tab must match.
        frames = Mock()
        handler = evennia.SESSION_HANDLER
        for name, stub in (("data_out", frames), ("disconnect", Mock())):
            patcher = patch.object(handler, name, stub)
            patcher.start()
            self.addCleanup(patcher.stop)
        self._lend()
        ensure_playable_lock(self.ysmay)
        ensure_playable_lock(self.ravenna)
        as_vael = self._web_signed_in(self.ilsa, 4430, puppet=self.vael)
        as_ravenna = self._web_signed_in(self.ravenna, 4431, puppet=self.ravenna)
        self._web_signed_in(self.ysmay, 4432, puppet=self.ysmay)
        frames.reset_mock()

        posed = self.api(self.account_of(self.ysmay)).post(
            SUBMIT_POSE,
            {
                "persona_id": persona_of(self.ysmay).pk,
                "scene_id": self.scene.pk,
                "content": "holds up the forged orders.",
                "client_request_id": str(uuid.uuid4()),
            },
            format="json",
        )
        self.assertEqual(posed.status_code, status.HTTP_201_CREATED, posed.data)

        for session in (as_vael, as_ravenna):
            sent = [call.kwargs for call in frames.call_args_list if call.args[0] is session]
            poses = [kw for kw in sent if "interaction" in kw]
            self.assertEqual(len(poses), 1, sent)
            notes = [
                kw["text"]
                for kw in sent
                if "text" in kw and not _text_options(kw["text"]).get("interaction_echo")
            ]
            self.assertEqual(notes, [], session.puppet)

    def test_a_resolved_action_reaches_web_sessions_once_and_telnet_as_text(self) -> None:
        # Bug G: the outcome's text lines went to web sessions too, because a live
        # websocket session's protocol key is "websocket", which the web test missed.
        self._lend()
        ensure_playable_lock(self.ysmay)
        frames = Mock()
        handler = evennia.SESSION_HANDLER
        for name, stub in (("data_out", frames), ("disconnect", Mock())):
            patcher = patch.object(handler, name, stub)
            patcher.start()
            self.addCleanup(patcher.stop)
        as_vael = self._web_signed_in(self.ilsa, 4440, puppet=self.vael)
        # Ysmay plays from a browser and a telnet client at once.
        as_ysmay = self._web_signed_in(self.ysmay, 4441, puppet=self.ysmay)
        on_telnet = self._web_signed_in(self.ysmay, 4442, puppet=self.ysmay, protocol="telnet")
        ActionTemplateFactory(name="Persuade", check_type=CheckTypeFactory(name="Persuasion"))
        frames.reset_mock()

        with self.captureOnCommitCallbacks(execute=True):
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
        self.assertEqual(persuaded.json()["status"], "resolved", persuaded.data)

        def sent_to(session):
            return [call.kwargs for call in frames.call_args_list if call.args[0] is session]

        for session in (as_vael, as_ysmay):
            sent = sent_to(session)
            outcomes = [
                kw
                for kw in sent
                if "interaction" in kw and "persuade" in kw["interaction"][1]["line"]
            ]
            self.assertEqual(len(outcomes), 1, sent)
            notes = [
                kw["text"]
                for kw in sent
                if "text" in kw and not _text_options(kw["text"]).get("interaction_echo")
            ]
            self.assertEqual(notes, [], session.puppet)
        telnet_lines = [_text_body(kw["text"]) for kw in sent_to(on_telnet) if "text" in kw]
        self.assertTrue(
            any("attempts to persuade Captain Vael" in line for line in telnet_lines),
            telnet_lines,
        )

    def test_a_live_pose_names_the_action_it_carries(self) -> None:
        # Bug I: a pose carrying an action reached other web sessions with no
        # action_links, so the NPC response card never found the pose.
        frames = Mock()
        handler = evennia.SESSION_HANDLER
        for name, stub in (("data_out", frames), ("disconnect", Mock())):
            patcher = patch.object(handler, name, stub)
            patcher.start()
            self.addCleanup(patcher.stop)
        self._lend()
        as_vael = self._web_signed_in(self.ilsa, 4450, puppet=self.vael)
        ActionTemplateFactory(name="Persuade", check_type=CheckTypeFactory(name="Persuasion"))
        ysmay_web = self.api(self.account_of(self.ysmay))
        with self.captureOnCommitCallbacks(execute=True):
            persuaded = ysmay_web.post(
                "/api/action-requests/",
                {
                    "scene": self.scene.pk,
                    "initiator_persona": persona_of(self.ysmay).pk,
                    "target_persona": persona_of(self.vael).pk,
                    "action_key": "persuade",
                },
                format="json",
            )
        self.assertEqual(persuaded.json()["status"], "resolved", persuaded.data)
        action = Interaction.objects.filter(mode=InteractionMode.ACTION).latest("pk")
        frames.reset_mock()

        posed = ysmay_web.post(
            SUBMIT_POSE,
            {
                "persona_id": persona_of(self.ysmay).pk,
                "scene_id": self.scene.pk,
                "content": "holds up the forged orders.",
                "action_link_ids": [action.pk],
                "client_request_id": str(uuid.uuid4()),
            },
            format="json",
        )
        self.assertEqual(posed.status_code, status.HTTP_201_CREATED, posed.data)

        live = [
            call.kwargs["interaction"][1]
            for call in frames.call_args_list
            if call.args[0] is as_vael and "interaction" in call.kwargs
        ]
        self.assertEqual(len(live), 1, live)
        self.assertEqual(
            [link["action_interaction"]["id"] for link in live[0]["action_links"]], [action.pk]
        )
        # The live frame names the same links the REST feed does for that pose.
        self.assertEqual(live[0]["action_links"], posed.json()["action_links"])

    def test_the_fights_aftermath_reaches_a_browser_once_and_telnet_as_text(self) -> None:
        # Round 7 bug K: "Aftermath: Victory." showed twice on /game, as the pushed
        # row and as a note, because the digest's text went to every session.
        from world.combat.aftermath import deliver_aftermath_digests
        from world.combat.constants import EncounterOutcome
        from world.combat.factories import (
            CombatEncounterFactory,
            CombatParticipantFactory,
        )

        frames = Mock()
        handler = evennia.SESSION_HANDLER
        for name, stub in (("data_out", frames), ("disconnect", Mock())):
            patcher = patch.object(handler, name, stub)
            patcher.start()
            self.addCleanup(patcher.stop)
        ensure_playable_lock(self.ysmay)
        in_browser = self._web_signed_in(self.ysmay, 4460, puppet=self.ysmay)
        on_telnet = self._web_signed_in(self.ysmay, 4461, puppet=self.ysmay, protocol="telnet")
        encounter = CombatEncounterFactory(
            scene=self.scene,
            room=self.room,
            outcome=EncounterOutcome.VICTORY,
            completed_at=timezone.now(),
        )
        CombatParticipantFactory(encounter=encounter, character_sheet=self.ysmay.sheet_data)
        frames.reset_mock()

        deliver_aftermath_digests(encounter)

        def sent_to(session):
            return [call.kwargs for call in frames.call_args_list if call.args[0] is session]

        web = sent_to(in_browser)
        rows = [kw["interaction"][1]["content"] for kw in web if "interaction" in kw]
        self.assertEqual(len(rows), 1, web)
        self.assertTrue(rows[0].startswith("Aftermath: Victory."), rows)
        self.assertEqual([kw for kw in web if "text" in kw], [])
        telnet_lines = [_text_body(kw["text"]) for kw in sent_to(on_telnet) if "text" in kw]
        self.assertTrue(
            any(line.startswith("Aftermath: Victory.") for line in telnet_lines), telnet_lines
        )

    def _dispatch_as_vael(self, account, key: str):
        return self.api(account).post(
            f"/api/actions/characters/{self.vael.pk}/dispatch/",
            {"ref": {"backend": "registry", "registry_key": key}, "kwargs": {}},
            format="json",
        )

    def test_the_web_dispatches_actions_as_whoever_plays_the_npc(self) -> None:
        # Round 8 item 12: every web dispatch as a lent NPC was a 403 before any
        # game rule ran; the endpoint checked tenure, not who may play the NPC.
        loan_id = self._lend()

        # Look with nothing named reaches the action's own answer, not a 403.
        looked = self._dispatch_as_vael(self.guide, "look")
        self.assertEqual(looked.status_code, status.HTTP_200_OK, looked.data)
        self.assertEqual(looked.json()["message"], "Look at what?")
        # A GM-only action reaches its own rule, which refuses the Guide.
        finish = self._dispatch_as_vael(self.guide, "finish_scene")
        self.assertEqual(finish.status_code, status.HTTP_200_OK, finish.data)
        self.assertEqual(
            finish.json()["message"], "Only the scene's GM or an owner can finish the scene."
        )
        # Lent away, the NPC is not its owner's to act as.
        self.assertEqual(
            self._dispatch_as_vael(self.gm, "look").status_code, status.HTTP_403_FORBIDDEN
        )

        taken = self.web(self.ravenna, "take_back_npc", loan_id=loan_id)
        self.assertTrue(taken.detail.success, taken.detail.message)
        self.assertEqual(self._dispatch_as_vael(self.gm, "look").status_code, status.HTTP_200_OK)
        self.assertEqual(
            self._dispatch_as_vael(self.guide, "look").status_code, status.HTTP_403_FORBIDDEN
        )

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
