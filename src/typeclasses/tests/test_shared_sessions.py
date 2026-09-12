"""Sessions share a character, and puppeting records the selection (#3812).

Arx 1 behaviour: a phone and a laptop on the same character are two windows
onto one object, and it does not matter which one you type in. That is
Evennia's ``MULTISESSION_MODE = 3``; what our code had to stop doing was
refusing a second session of our own on a character we already puppet.
"""

from __future__ import annotations

from unittest.mock import Mock

from django.conf import settings
from django.test import TestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from typeclasses.tests.test_account_puppet_broadcast import (
    _patch_super_puppet,
    _restore_super_puppet,
    _session_mock,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import RosterEntryFactory, RosterFactory, RosterTenureFactory
from world.roster.models import RosterType


class SharedSessionsSettingsTests(TestCase):
    def test_sessions_share_a_puppet_and_puppets_are_unlimited(self) -> None:
        self.assertEqual(settings.MULTISESSION_MODE, 3)
        self.assertIsNone(settings.MAX_NR_SIMULTANEOUS_PUPPETS)


class SharedSessionsTestCase(TestCase):
    def setUp(self) -> None:
        self.account = AccountFactory()
        self.character = CharacterFactory(db_key="Bob")
        sheet = CharacterSheetFactory(character=self.character)
        self.entry = RosterEntryFactory(
            character_sheet=sheet,
            roster=RosterFactory(name=RosterType.ACTIVE, roster_type=RosterType.ACTIVE),
        )
        RosterTenureFactory(player_data=self.account.player_data, roster_entry=self.entry)


class SecondSessionSharesTheCharacterTests(SharedSessionsTestCase):
    def test_can_puppet_a_character_another_of_my_sessions_already_has(self) -> None:
        other = _session_mock(10, puppet=self.character)
        self.account.sessions.all = lambda: [other]

        can, reason = self.account.can_puppet_character(self.character)

        self.assertTrue(can, reason)

    def test_second_session_puppets_without_unpuppeting_the_first(self) -> None:
        first = _session_mock(10, puppet=self.character)
        second = _session_mock(11)
        self.account.sessions.all = lambda: [first, second]
        unpuppeted: list = []
        self.account.unpuppet_object = lambda session: unpuppeted.append(session)

        def fake_super_puppet(_self, session, obj):
            session.puppet = obj

        original = _patch_super_puppet(self.account, fake_super_puppet)
        try:
            ok, _msg = self.account.puppet_character_in_session(self.character, second)
        finally:
            _restore_super_puppet(self.account, original)

        self.assertTrue(ok)
        self.assertIs(second.puppet, self.character)
        self.assertIs(first.puppet, self.character)
        self.assertEqual(unpuppeted, [])


class RepeatedIcIsIdempotentTests(SharedSessionsTestCase):
    def test_ic_for_the_character_this_session_already_puppets_is_a_no_op(self) -> None:
        """The web client sends ``@ic <name>`` on every socket open; login already puppeted it."""
        session = _session_mock(10, puppet=self.character)
        self.account.sessions.all = lambda: [session]
        super_called = Mock()

        original = _patch_super_puppet(self.account, super_called)
        try:
            ok, message = self.account.puppet_character_in_session(self.character, session)
        finally:
            _restore_super_puppet(self.account, original)

        self.assertTrue(ok)
        self.assertIn("Already controlling Bob", message)
        super_called.assert_not_called()


class PuppetingRecordsTheSelectionTests(SharedSessionsTestCase):
    def test_a_successful_puppet_sets_the_durable_selection(self) -> None:
        session = _session_mock(10)
        self.account.sessions.all = lambda: [session]
        self.assertIsNone(self.account.player_data.selected_entry_id)

        def fake_super_puppet(_self, sess, obj):
            sess.puppet = obj

        original = _patch_super_puppet(self.account, fake_super_puppet)
        try:
            self.account.puppet_object(session, self.character)
        finally:
            _restore_super_puppet(self.account, original)

        self.account.player_data.refresh_from_db()
        self.assertEqual(self.account.player_data.selected_entry_id, self.entry.pk)

    def test_a_refused_puppet_records_nothing(self) -> None:
        session = _session_mock(10)
        self.account.sessions.all = lambda: [session]

        original = _patch_super_puppet(self.account, lambda _self, _sess, _obj: None)
        try:
            self.account.puppet_object(session, self.character)
        finally:
            _restore_super_puppet(self.account, original)

        self.account.player_data.refresh_from_db()
        self.assertIsNone(self.account.player_data.selected_entry_id)

    def test_puppeting_an_object_with_no_roster_entry_is_fine(self) -> None:
        prop = CharacterFactory(db_key="Prop")
        session = _session_mock(10)
        self.account.sessions.all = lambda: [session]

        def fake_super_puppet(_self, sess, obj):
            sess.puppet = obj

        original = _patch_super_puppet(self.account, fake_super_puppet)
        try:
            self.account.puppet_object(session, prop)
        finally:
            _restore_super_puppet(self.account, original)

        self.account.player_data.refresh_from_db()
        self.assertIsNone(self.account.player_data.selected_entry_id)
