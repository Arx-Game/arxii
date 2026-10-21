"""Journeys for playing the character you made (#4544).

A character made through character creation finalize kept Evennia's default puppet
lock, ``puppet:pperm(Developer)``. The player held the tenure, passed the roster
check, and was then refused with "You don't have permission to puppet". These
journeys finalize a draft through the real endpoints and have the player take the
character up the two ways a player does: the browser's ``puppet`` request and
telnet ``@ic``. No journey sets a lock by hand.
"""

from __future__ import annotations

from unittest.mock import Mock, patch

import evennia
from evennia.objects.models import ObjectDB
from evennia.server.serversession import ServerSession
from rest_framework import status

from evennia_extensions.factories import AccountFactory, EmailAddressFactory
from integration_tests.harness import JourneyCase
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory, GMTableFactory, seed_default_gm_level_caps
from world.roster.factories import PlayerDataFactory
from world.roster.models import RosterApplication, RosterEntry, RosterTenure

NO_PERMISSION = "You don't have permission to puppet"


class PlayingTheCharacterYouMade(FinalizationTestMixin, JourneyCase):
    """Wren makes a character; Ysolde (staff) approves it; Wren plays it."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls._setup_finalization_base(cls, prefix="Playable", height_min=700, height_max=800)
        cls.staff = AccountFactory(is_staff=True)
        cls.staff_data = PlayerDataFactory(account=cls.staff)
        cls.player = AccountFactory()
        cls.player_data = PlayerDataFactory(account=cls.player)
        EmailAddressFactory(user=cls.player, email=cls.player.email, verified=True, primary=True)

    # -- helpers --------------------------------------------------------------

    def _draft(self, owner, first_name: str):
        self.account = owner
        return self._create_base_draft(first_name=first_name)

    def _character_of_entry(self, entry_id: int) -> ObjectDB:
        entry = RosterEntry.objects.get(pk=entry_id)
        return ObjectDB.objects.get(pk=entry.character_sheet_id)

    def _session(self, account, sessid: int, protocol: str) -> ServerSession:
        """A session signed in as ``account`` and puppeting nothing yet."""
        handler = evennia.SESSION_HANDLER
        for name in ("data_out", "disconnect"):
            patcher = patch.object(handler, name, Mock())
            patcher.start()
            self.addCleanup(patcher.stop)
        dummy = ServerSession()
        dummy.init_session(protocol, ("localhost", "testmode"), handler)
        dummy.sessid = sessid
        handler.portal_connect(dummy.get_sync_data())
        session = handler.session_from_sessid(sessid)
        self.addCleanup(handler.pop, sessid, None)
        handler.login(session, account, testmode=True)
        return session

    def _web_puppet(self, session: ServerSession, name: str) -> list[dict]:
        """The browser's ``puppet`` request; returns the error frames it was sent."""
        sent: list[dict] = []
        original = session.msg

        def record(*args, **kwargs):
            if "command_error" in kwargs:
                sent.append(kwargs["command_error"])
            return original(*args, **kwargs)

        with patch.object(session, "msg", record):
            session.data_in(puppet=([], {"character": name}))
        return sent

    def _telnet_ic(self, account, session: ServerSession, name: str) -> str:
        """``@ic <name>`` typed at the account's session, the way telnet does."""
        box = self.mailbox(account)
        start = len(box.lines)
        account.execute_cmd(f"@ic {name}", session=session)
        return "\n".join(box.lines[start:])

    def _assert_plays_on_web_and_telnet(self, account, character: ObjectDB, *, base: int) -> None:
        # The browser.
        web = self._session(account, base, "websocket")
        errors = self._web_puppet(web, character.key)
        self.assertEqual(errors, [])
        self.assertIs(web.puppet, character)
        account.unpuppet_object(web)
        self.assertIsNone(web.puppet)
        # Telnet.
        telnet = self._session(account, base + 1, "telnet")
        told = self._telnet_ic(account, telnet, character.key)
        self.assertNotIn(NO_PERMISSION, told)
        self.assertIs(telnet.puppet, character)

    # -- journeys -------------------------------------------------------------

    def test_a_player_made_character_is_playable_once_approved(self) -> None:
        draft = self._draft(self.player, "Wren")
        player_api = self.api(self.player)
        submitted = player_api.post(
            f"/api/character-creation/drafts/{draft.pk}/submit/", {}, format="json"
        )
        self.assertEqual(submitted.status_code, status.HTTP_201_CREATED, submitted.content)
        application_id = submitted.json()["id"]

        staff_api = self.api(self.staff)
        for step in ("claim", "approve"):
            response = staff_api.post(
                f"/api/character-creation/applications/{application_id}/{step}/", {}, format="json"
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)

        tenure = RosterTenure.objects.get(player_data=self.player_data)
        character = ObjectDB.objects.get(pk=tenure.roster_entry.character_sheet_id)
        self._assert_plays_on_web_and_telnet(self.player, character, base=4544)

    def test_a_staff_added_character_is_playable_once_a_player_is_seated(self) -> None:
        draft = self._draft(self.staff, "Corin")
        added = self.api(self.staff).post(
            f"/api/character-creation/drafts/{draft.pk}/add-to-roster/", {}, format="json"
        )
        self.assertEqual(added.status_code, status.HTTP_200_OK, added.content)
        character = ObjectDB.objects.get(pk=added.json()["character_id"])
        entry = RosterEntry.objects.get(character_sheet_id=character.pk)

        applied = self.api(self.player).post(
            f"/api/roster/entries/{entry.pk}/apply/",
            {"message": "I would like to play Corin because the character reads well."},
            format="json",
        )
        self.assertEqual(applied.status_code, status.HTTP_204_NO_CONTENT, applied.content)
        application = RosterApplication.objects.get(player_data=self.player_data)
        self.assertTrue(application.approve(self.staff_data))

        self._assert_plays_on_web_and_telnet(self.player, character, base=4546)


class PlayingAGmMadeCharacter(FinalizationTestMixin, JourneyCase):
    """A GM finalizes a character for their table; the GM plays the Story NPC it binds."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls._setup_finalization_base(cls, prefix="Table", height_min=700, height_max=800)
        seed_default_gm_level_caps()
        cls.gm = GMProfileFactory(level=GMLevel.JUNIOR)
        PlayerDataFactory(account=cls.gm.account)
        cls.table = GMTableFactory(gm=cls.gm)

    def test_a_gm_plays_the_story_npc_they_finalized(self) -> None:
        self.account = self.gm.account
        draft = self._create_base_draft(first_name="Aurelius")
        response = self.api(self.gm.account).post(
            f"/api/character-creation/drafts/{draft.pk}/finalize-gm/",
            {
                "target_table": self.table.pk,
                "story_title": "The Grand Design",
                "claim_as_npc": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        character = ObjectDB.objects.get(pk=response.json()["character_id"])

        handler = evennia.SESSION_HANDLER
        for name in ("data_out", "disconnect"):
            patcher = patch.object(handler, name, Mock())
            patcher.start()
            self.addCleanup(patcher.stop)
        dummy = ServerSession()
        dummy.init_session("telnet", ("localhost", "testmode"), handler)
        dummy.sessid = 4548
        handler.portal_connect(dummy.get_sync_data())
        session = handler.session_from_sessid(4548)
        self.addCleanup(handler.pop, 4548, None)
        handler.login(session, self.gm.account, testmode=True)

        box = self.mailbox(self.gm.account)
        start = len(box.lines)
        self.gm.account.execute_cmd(f"@ic {character.key}", session=session)
        told = "\n".join(box.lines[start:])
        self.assertNotIn(NO_PERMISSION, told)
        self.assertIs(session.puppet, character)
