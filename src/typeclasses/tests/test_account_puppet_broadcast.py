"""Tests for Account puppet_changed broadcast on @ic swaps."""

from unittest.mock import MagicMock

from django.test import TestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import (
    RosterEntryFactory,
    RosterFactory,
    RosterTenureFactory,
)
from world.roster.models import RosterType


class PuppetCharacterBroadcastTests(TestCase):
    """puppet_character_in_session should broadcast puppet_changed to all sessions."""

    def setUp(self) -> None:
        self.account = AccountFactory()
        self.character = CharacterFactory(db_key="Bob")
        sheet = CharacterSheetFactory(character=self.character)
        entry = RosterEntryFactory(
            character_sheet=sheet,
            roster=RosterFactory(name=RosterType.ACTIVE),
        )
        RosterTenureFactory(
            player_data=self.account.player_data,
            roster_entry=entry,
        )

    def test_puppet_swap_broadcasts_to_all_sessions(self) -> None:
        sess1 = MagicMock(sessid=10, puppet=None)
        sess2 = MagicMock(sessid=11, puppet=None)
        self.account.sessions.all = lambda: [sess1, sess2]

        # Stub puppet_object so we don't need a real Evennia session
        self.account.puppet_object = MagicMock()

        success, _msg = self.account.puppet_character_in_session(self.character, sess1)
        assert success

        # Both sessions should have received a puppet_changed message
        for sess in (sess1, sess2):
            puppet_calls = [
                call
                for call in sess.msg.call_args_list
                if call.kwargs.get("type") == "puppet_changed"
            ]
            assert len(puppet_calls) >= 1, f"sess {sess.sessid} got no puppet_changed"
            payload = puppet_calls[0].kwargs["args"][0]
            assert payload["session_id"] == 10
            assert payload["character_id"] == self.character.id
            assert payload["character_name"] == self.character.key

    def test_failed_puppet_does_not_broadcast(self) -> None:
        sess1 = MagicMock(sessid=10, puppet=None)
        self.account.sessions.all = lambda: [sess1]
        # Force can_puppet_character to return False
        self.account.can_puppet_character = lambda _c: (False, "nope")
        success, _msg = self.account.puppet_character_in_session(self.character, sess1)
        assert not success
        puppet_calls = [
            call for call in sess1.msg.call_args_list if call.kwargs.get("type") == "puppet_changed"
        ]
        assert puppet_calls == []


class UnpuppetBroadcastTests(TestCase):
    """unpuppet_object should broadcast puppet_changed to all sessions."""

    def setUp(self) -> None:
        super().setUp()
        self.account = AccountFactory()
        self.character = CharacterFactory(db_key="Bob")
        sheet = CharacterSheetFactory(character=self.character)
        entry = RosterEntryFactory(
            character_sheet=sheet,
            roster=RosterFactory(name=RosterType.ACTIVE),
        )
        RosterTenureFactory(
            player_data=self.account.player_data,
            roster_entry=entry,
        )

    def test_unpuppet_broadcasts_with_null_character(self) -> None:
        sess1 = MagicMock(sessid=10)
        sess1.puppet = self.character
        sess2 = MagicMock(sessid=11, puppet=None)
        self.account.sessions.all = lambda: [sess1, sess2]

        self.account.unpuppet_object(sess1)

        for sess in (sess1, sess2):
            puppet_calls = [
                call
                for call in sess.msg.call_args_list
                if call.kwargs.get("type") == "puppet_changed"
            ]
            assert len(puppet_calls) >= 1, f"sess {sess.sessid} got no puppet_changed"
            payload = puppet_calls[-1].kwargs["args"][0]
            assert payload["session_id"] == 10
            assert payload["character_id"] is None
            assert payload["character_name"] is None
