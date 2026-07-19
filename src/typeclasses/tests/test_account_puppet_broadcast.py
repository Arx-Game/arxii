"""Tests for Account puppet_changed broadcast on @ic swaps."""

from unittest.mock import MagicMock

from django.test import TestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from typeclasses.accounts import Account
from web.webclient.message_types import WebsocketMessageType
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import (
    RosterEntryFactory,
    RosterFactory,
    RosterTenureFactory,
)
from world.roster.models import RosterType
from world.vitals.factories import CharacterVitalsFactory


def _patch_super_puppet(account, fake) -> object:
    """Replace the parent class's puppet_object with `fake`; return the original.

    The Account override calls `super().puppet_object(...)`. To exercise the
    override (and its post-call broadcast) without a real Evennia session,
    we stub the parent's puppet_object on the MRO. Returns the original
    callable so callers can restore it.
    """
    parent = type(account).__mro__[1]
    original = parent.puppet_object
    parent.puppet_object = fake
    return original


def _restore_super_puppet(account, original) -> None:
    """Restore the parent class's puppet_object to `original`."""
    parent = type(account).__mro__[1]
    parent.puppet_object = original


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

        # Stub super().puppet_object to simulate Evennia setting session.puppet
        def fake_super_puppet(self_, session, obj):
            session.puppet = obj

        original = _patch_super_puppet(self.account, fake_super_puppet)
        try:
            success, _msg = self.account.puppet_character_in_session(self.character, sess1)
        finally:
            _restore_super_puppet(self.account, original)

        assert success

        # Both sessions should have received a puppet_changed message
        for sess in (sess1, sess2):
            puppet_calls = [
                call
                for call in sess.msg.call_args_list
                if call.kwargs.get("type") == WebsocketMessageType.PUPPET_CHANGED.value
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
            call
            for call in sess1.msg.call_args_list
            if call.kwargs.get("type") == WebsocketMessageType.PUPPET_CHANGED.value
        ]
        assert puppet_calls == []


class PuppetObjectDirectCallBroadcastTests(TestCase):
    """Calling puppet_object directly (not via puppet_character_in_session)
    should still broadcast puppet_changed. This covers Evennia's internal
    paths: multisession takeover, session reuse, etc."""

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

    def test_direct_puppet_object_call_broadcasts(self) -> None:
        sess = MagicMock(sessid=10, puppet=None)
        self.account.sessions.all = lambda: [sess]

        # Stub super().puppet_object to simulate Evennia setting session.puppet
        def fake_super_puppet(self_, session, obj):
            session.puppet = obj

        original = _patch_super_puppet(self.account, fake_super_puppet)
        try:
            self.account.puppet_object(sess, self.character)
        finally:
            _restore_super_puppet(self.account, original)

        puppet_calls = [
            c
            for c in sess.msg.call_args_list
            if c.kwargs.get("type") == WebsocketMessageType.PUPPET_CHANGED.value
        ]
        assert len(puppet_calls) == 1
        payload = puppet_calls[0].kwargs["args"][0]
        assert payload["character_id"] == self.character.id
        assert payload["character_name"] == self.character.key

    def test_failed_puppet_object_does_not_broadcast(self) -> None:
        """If super().puppet_object early-returns without setting puppet,
        broadcast is suppressed."""
        sess = MagicMock(sessid=10, puppet=None)
        self.account.sessions.all = lambda: [sess]

        def fake_super_puppet_fails(self_, session, obj):
            # session.puppet stays None — simulates an early-return path
            pass

        original = _patch_super_puppet(self.account, fake_super_puppet_fails)
        try:
            self.account.puppet_object(sess, self.character)
        finally:
            _restore_super_puppet(self.account, original)

        puppet_calls = [
            c
            for c in sess.msg.call_args_list
            if c.kwargs.get("type") == WebsocketMessageType.PUPPET_CHANGED.value
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
                if call.kwargs.get("type") == WebsocketMessageType.PUPPET_CHANGED.value
            ]
            assert len(puppet_calls) >= 1, f"sess {sess.sessid} got no puppet_changed"
            payload = puppet_calls[-1].kwargs["args"][0]
            assert payload["session_id"] == 10
            assert payload["character_id"] is None
            assert payload["character_name"] is None


class CanPuppetForSeanceTests(TestCase):
    """Account.can_puppet_for_seance (#2393) — narrow retired-login bypass."""

    def test_denies_non_retired_character(self) -> None:
        account = AccountFactory()
        sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=sheet)
        can_puppet, _reason = account.can_puppet_for_seance(sheet.character)
        self.assertFalse(can_puppet)

    def _retired_sheet_with_accepted_open_offer(self):
        """Build a retired, dead CharacterSheet owned (via tenure) by a real
        account, with an ACCEPTED SeanceManifestationOffer whose ceremony is
        still OPEN. Mirrors RespondToSeanceOfferTests in
        world/ceremonies/tests/test_services.py."""
        from django.utils import timezone

        from world.ceremonies.constants import CeremonyTypeKey
        from world.ceremonies.factories import CeremonyTypeFactory
        from world.ceremonies.services import open_ceremony, respond_to_seance_offer
        from world.roster.factories import PlayerDataFactory
        from world.vitals.constants import CharacterLifeState
        from world.worship.factories import WorshippedBeingFactory
        from world.worship.models import WorshipDeclaration

        sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=sheet, life_state=CharacterLifeState.DEAD)
        sheet.vitals.retired_at = timezone.now()
        sheet.vitals.save(update_fields=["retired_at"])

        player_data = PlayerDataFactory()
        entry = RosterEntryFactory(character_sheet=sheet)
        RosterTenureFactory(roster_entry=entry, player_data=player_data)
        account = player_data.account

        CeremonyTypeFactory(key=CeremonyTypeKey.SEANCE, name="Seance")
        from evennia_extensions.factories import RoomProfileFactory

        location = RoomProfileFactory()

        officiant_sheet = CharacterSheetFactory()
        officiant_persona = officiant_sheet.primary_persona
        being = WorshippedBeingFactory()
        WorshipDeclaration.objects.create(character_sheet=officiant_sheet, public_being=being)

        ceremony = open_ceremony(
            officiant_persona=officiant_persona,
            type_key=CeremonyTypeKey.SEANCE,
            honoree_sheets=[sheet],
            location_profile=location,
        )
        offer = ceremony.honorees.get(honoree_sheet=sheet).seance_offer
        respond_to_seance_offer(offer, account=account, accept=True)

        return sheet, account

    def test_grants_retired_character_with_accepted_open_offer(self) -> None:
        sheet, account = self._retired_sheet_with_accepted_open_offer()
        can_puppet, reason = account.can_puppet_for_seance(sheet.character)
        self.assertTrue(can_puppet)
        self.assertEqual(reason, "")

    def test_denies_wrong_account(self) -> None:
        from world.roster.factories import PlayerDataFactory

        sheet, _account = self._retired_sheet_with_accepted_open_offer()
        stranger = PlayerDataFactory().account
        can_puppet, _reason = stranger.can_puppet_for_seance(sheet.character)
        self.assertFalse(can_puppet)


# Silence unused-import warning for Account; imported for IDE/type clarity.
_ = Account
