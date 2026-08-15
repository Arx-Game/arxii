"""Tests for the negotiated trade state machine (#2990).

Covers the spec's anti-dupe invariants: double-stake rejected, a pulled-out
item aborts the whole trade atomically, coin is checked both at stage and at
execute, any offer mutation resets both confirms, double-execute is
impossible, and cancel moves nothing (stakes are declarations, not escrow).
"""

from __future__ import annotations

from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.currency.services import get_or_create_purse, transfer
from world.items.constants import OwnershipEventType
from world.items.exceptions import NotInPossession, RecipientConsentDenied, RecipientNotAdjacent
from world.items.factories import ItemInstanceFactory
from world.items.models import ItemInstance, OwnershipEvent
from world.items.trade.exceptions import (
    NotATradeParty,
    SelfTradeNotAllowed,
    TradeAlreadyResolved,
    TradeCoinOverBalance,
    TradeItemAlreadyStaked,
    TradeItemUnavailable,
    TradeNotActive,
    TradeNotProposed,
    TradeSessionOpenAlready,
)
from world.items.trade.models import TradeItemStake, TradeSession
from world.items.trade.services import (
    accept_trade,
    cancel_trade,
    confirm,
    propose_trade,
    set_coin_offer,
    stake_item,
    unstake_item,
)


class TradeTestBase(TestCase):
    def setUp(self) -> None:
        self.room = ObjectDBFactory(
            db_key="TradeRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.alice = CharacterFactory(db_key="TradeAlice", location=self.room)
        self.alice_sheet = CharacterSheetFactory(character=self.alice)
        self.bob = CharacterFactory(db_key="TradeBob", location=self.room)
        self.bob_sheet = CharacterSheetFactory(character=self.bob)

    def _held_item(self, sheet, key: str = "Trinket") -> ItemInstance:
        obj = ObjectDBFactory(db_key=key, location=sheet.character)
        return ItemInstanceFactory(game_object=obj, holder_character_sheet=sheet)

    def _fund(self, sheet, amount: int) -> None:
        transfer(amount=amount, reason="test seed", to_purse=get_or_create_purse(sheet))

    def _active_session(self) -> TradeSession:
        session = propose_trade(self.alice_sheet, self.bob_sheet)
        return accept_trade(session, self.bob_sheet)


class ProposeAcceptTests(TradeTestBase):
    def test_self_trade_rejected(self) -> None:
        with self.assertRaises(SelfTradeNotAllowed):
            propose_trade(self.alice_sheet, self.alice_sheet)

    def test_non_adjacent_parties_rejected(self) -> None:
        elsewhere = ObjectDBFactory(db_key="Elsewhere", db_typeclass_path="typeclasses.rooms.Room")
        self.bob.location = elsewhere
        self.bob.save()
        with self.assertRaises(RecipientNotAdjacent):
            propose_trade(self.alice_sheet, self.bob_sheet)

    def test_existing_open_session_blocks_a_second_either_direction(self) -> None:
        propose_trade(self.alice_sheet, self.bob_sheet)
        with self.assertRaises(TradeSessionOpenAlready):
            propose_trade(self.alice_sheet, self.bob_sheet)
        with self.assertRaises(TradeSessionOpenAlready):
            propose_trade(self.bob_sheet, self.alice_sheet)

    def test_accept_requires_the_invited_party(self) -> None:
        session = propose_trade(self.alice_sheet, self.bob_sheet)
        with self.assertRaises(NotATradeParty):
            accept_trade(session, self.alice_sheet)

    def test_accept_moves_proposed_to_active(self) -> None:
        session = propose_trade(self.alice_sheet, self.bob_sheet)
        accept_trade(session, self.bob_sheet)
        session.refresh_from_db()
        self.assertEqual(session.status, TradeSession.Status.ACTIVE)

    def test_accept_twice_rejected(self) -> None:
        session = self._active_session()
        with self.assertRaises(TradeNotProposed):
            accept_trade(session, self.bob_sheet)


class StakeTests(TradeTestBase):
    def test_stake_before_accept_rejected(self) -> None:
        session = propose_trade(self.alice_sheet, self.bob_sheet)
        item = self._held_item(self.alice_sheet)
        with self.assertRaises(TradeNotActive):
            stake_item(session, self.alice_sheet, item)

    def test_stake_item_not_held_rejected(self) -> None:
        session = self._active_session()
        item = self._held_item(self.bob_sheet)
        with self.assertRaises(NotInPossession):
            stake_item(session, self.alice_sheet, item)

    def test_same_item_staked_twice_in_one_session_rejected(self) -> None:
        session = self._active_session()
        item = self._held_item(self.alice_sheet)
        stake_item(session, self.alice_sheet, item)
        with self.assertRaises(TradeItemAlreadyStaked):
            stake_item(session, self.alice_sheet, item)

    def test_item_already_staked_in_another_open_session_rejected(self) -> None:
        session_a = self._active_session()
        item = self._held_item(self.alice_sheet)
        stake_item(session_a, self.alice_sheet, item)

        carol = CharacterFactory(db_key="TradeCarol", location=self.room)
        carol_sheet = CharacterSheetFactory(character=carol)
        session_b = propose_trade(self.alice_sheet, carol_sheet)
        accept_trade(session_b, carol_sheet)
        with self.assertRaises(TradeItemAlreadyStaked):
            stake_item(session_b, self.alice_sheet, item)

    def test_stake_resets_both_confirms(self) -> None:
        session = self._active_session()
        item_a = self._held_item(self.alice_sheet, key="A")
        item_b = self._held_item(self.alice_sheet, key="B")
        stake_item(session, self.alice_sheet, item_a)
        confirm(session, self.alice_sheet)
        session.refresh_from_db()
        self.assertTrue(session.initiator_confirmed)

        stake_item(session, self.alice_sheet, item_b)
        session.refresh_from_db()
        self.assertFalse(session.initiator_confirmed)
        self.assertFalse(session.counterparty_confirmed)

    def test_unstake_removes_the_stake_and_resets_confirms(self) -> None:
        session = self._active_session()
        item = self._held_item(self.alice_sheet)
        stake = stake_item(session, self.alice_sheet, item)
        confirm(session, self.alice_sheet)

        unstake_item(stake)
        self.assertFalse(TradeItemStake.objects.filter(pk=stake.pk).exists())
        session.refresh_from_db()
        self.assertFalse(session.initiator_confirmed)

    def test_hot_goods_consent_blocks_stake(self) -> None:
        from world.consent.constants import ConsentMode
        from world.consent.services import (
            receiving_stolen_goods_category,
            set_social_consent_category_rule,
            set_social_consent_preference,
        )
        from world.roster.factories import RosterEntryFactory, RosterTenureFactory

        session = self._active_session()
        item = self._held_item(self.alice_sheet)
        victim_sheet = CharacterSheetFactory()
        OwnershipEvent.objects.create(
            item_instance=item,
            event_type=OwnershipEventType.STOLEN,
            from_character_sheet=victim_sheet,
            to_character_sheet=self.alice_sheet,
        )
        bob_tenure = RosterTenureFactory(
            roster_entry=RosterEntryFactory(character_sheet=self.bob_sheet),
            end_date=None,
        )
        preference = set_social_consent_preference(bob_tenure, allow_social_actions=True)
        set_social_consent_category_rule(
            preference, receiving_stolen_goods_category(), ConsentMode.ALLOWLIST
        )

        with self.assertRaises(RecipientConsentDenied):
            stake_item(session, self.alice_sheet, item)

    def test_can_give_false_blocks_stake(self) -> None:
        """A cursed/soulbound-style ``can_give`` package refusal blocks staking (#2990 review).

        No live package implements this hook today, but ``stake_item`` must honor
        it the same way ``give()`` does the moment one exists.
        """
        session = self._active_session()
        item = self._held_item(self.alice_sheet)

        with patch("flows.object_states.item_state.ItemState.can_give", return_value=False):
            with self.assertRaises(NotInPossession):
                stake_item(session, self.alice_sheet, item)

        self.assertFalse(TradeItemStake.objects.filter(item_instance=item).exists())


class CoinOfferTests(TradeTestBase):
    def test_over_balance_rejected_at_stage_time(self) -> None:
        session = self._active_session()
        self._fund(self.alice_sheet, 10)
        with self.assertRaises(TradeCoinOverBalance):
            set_coin_offer(session, self.alice_sheet, 50)

    def test_negative_amount_rejected(self) -> None:
        session = self._active_session()
        with self.assertRaises(ValidationError):
            set_coin_offer(session, self.alice_sheet, -1)

    def test_setting_coin_resets_confirms(self) -> None:
        session = self._active_session()
        self._fund(self.alice_sheet, 100)
        confirm(session, self.bob_sheet)
        session.refresh_from_db()
        self.assertTrue(session.counterparty_confirmed)

        set_coin_offer(session, self.alice_sheet, 25)
        session.refresh_from_db()
        self.assertFalse(session.counterparty_confirmed)
        self.assertEqual(session.initiator_coppers, 25)


class ExecuteTradeTests(TradeTestBase):
    def test_barter_round_trip_moves_items_and_coin_both_directions(self) -> None:
        session = self._active_session()
        alice_item = self._held_item(self.alice_sheet, key="AliceSword")
        bob_item = self._held_item(self.bob_sheet, key="BobShield")
        self._fund(self.alice_sheet, 100)
        self._fund(self.bob_sheet, 100)

        stake_item(session, self.alice_sheet, alice_item)
        stake_item(session, self.bob_sheet, bob_item)
        set_coin_offer(session, self.alice_sheet, 30)
        set_coin_offer(session, self.bob_sheet, 10)

        confirm(session, self.alice_sheet)
        confirm(session, self.bob_sheet)

        session.refresh_from_db()
        self.assertEqual(session.status, TradeSession.Status.COMPLETED)
        self.assertIsNotNone(session.resolved_at)

        alice_item.refresh_from_db()
        bob_item.refresh_from_db()
        self.assertEqual(alice_item.holder_character_sheet_id, self.bob_sheet.pk)
        self.assertEqual(bob_item.holder_character_sheet_id, self.alice_sheet.pk)

        self.assertEqual(get_or_create_purse(self.alice_sheet).balance, 80)
        self.assertEqual(get_or_create_purse(self.bob_sheet).balance, 120)

        events = OwnershipEvent.objects.filter(item_instance__in=[alice_item, bob_item])
        self.assertEqual(events.count(), 2)
        for event in events:
            self.assertEqual(event.event_type, OwnershipEventType.TRANSFERRED)
            self.assertEqual(event.notes, f"trade #{session.pk}")

    def test_double_execute_is_impossible(self) -> None:
        session = self._active_session()
        confirm(session, self.alice_sheet)
        confirm(session, self.bob_sheet)
        session.refresh_from_db()
        self.assertEqual(session.status, TradeSession.Status.COMPLETED)

        with self.assertRaises(TradeNotActive):
            confirm(session, self.alice_sheet)

    def test_item_pulled_out_mid_negotiation_aborts_whole_trade(self) -> None:
        session = self._active_session()
        alice_item = self._held_item(self.alice_sheet, key="AliceRing")
        stake = stake_item(session, self.alice_sheet, alice_item)
        confirm(session, self.bob_sheet)

        # The item leaves alice's possession behind the trade's back (e.g. a
        # separate GiveAction) before the second confirm executes the swap.
        alice_item.holder_character_sheet = self.bob_sheet
        alice_item.save(update_fields=["holder_character_sheet"])

        with self.assertRaises(TradeItemUnavailable):
            confirm(session, self.alice_sheet)

        session.refresh_from_db()
        self.assertEqual(session.status, TradeSession.Status.ACTIVE)
        self.assertFalse(session.initiator_confirmed)
        self.assertFalse(session.counterparty_confirmed)
        self.assertTrue(TradeItemStake.objects.filter(pk=stake.pk).exists())

    def test_can_give_false_between_confirm_and_execute_aborts_whole_trade(self) -> None:
        """A ``can_give`` package refusal appearing between stage and execute (#2990 review).

        Mirrors the stale-stake abort: the whole trade fails atomically, the
        session survives ``ACTIVE`` with both confirms reset, and the stake
        row is untouched — same shape as an item pulled out from under the
        deal, since the two are the same "is this item still giveable" gate.
        """
        session = self._active_session()
        alice_item = self._held_item(self.alice_sheet, key="AliceCursedRing")
        stake = stake_item(session, self.alice_sheet, alice_item)
        confirm(session, self.bob_sheet)

        with patch("flows.object_states.item_state.ItemState.can_give", return_value=False):
            with self.assertRaises(TradeItemUnavailable):
                confirm(session, self.alice_sheet)

        session.refresh_from_db()
        self.assertEqual(session.status, TradeSession.Status.ACTIVE)
        self.assertFalse(session.initiator_confirmed)
        self.assertFalse(session.counterparty_confirmed)
        self.assertTrue(TradeItemStake.objects.filter(pk=stake.pk).exists())
        alice_item.refresh_from_db()
        self.assertEqual(alice_item.holder_character_sheet_id, self.alice_sheet.pk)

    def test_purse_spent_between_stage_and_confirm_rolls_back(self) -> None:
        session = self._active_session()
        self._fund(self.alice_sheet, 50)
        set_coin_offer(session, self.alice_sheet, 50)
        confirm(session, self.bob_sheet)

        # Alice spends her coin elsewhere before the trade executes.
        transfer(
            amount=50,
            reason="spent elsewhere",
            from_purse=get_or_create_purse(self.alice_sheet),
        )

        with self.assertRaises(ValidationError):
            confirm(session, self.alice_sheet)

        session.refresh_from_db()
        self.assertEqual(session.status, TradeSession.Status.ACTIVE)
        self.assertFalse(session.initiator_confirmed)
        self.assertFalse(session.counterparty_confirmed)
        self.assertEqual(get_or_create_purse(self.bob_sheet).balance, 0)


class CancelTests(TradeTestBase):
    def test_cancel_moves_nothing(self) -> None:
        session = self._active_session()
        item = self._held_item(self.alice_sheet)
        self._fund(self.alice_sheet, 100)
        stake_item(session, self.alice_sheet, item)
        set_coin_offer(session, self.alice_sheet, 40)

        cancel_trade(session, self.bob_sheet)

        session.refresh_from_db()
        self.assertEqual(session.status, TradeSession.Status.CANCELLED)
        item.refresh_from_db()
        self.assertEqual(item.holder_character_sheet_id, self.alice_sheet.pk)
        self.assertEqual(get_or_create_purse(self.alice_sheet).balance, 100)

    def test_cancel_at_proposed(self) -> None:
        session = propose_trade(self.alice_sheet, self.bob_sheet)
        cancel_trade(session, self.alice_sheet)
        session.refresh_from_db()
        self.assertEqual(session.status, TradeSession.Status.CANCELLED)

    def test_cancel_twice_rejected(self) -> None:
        session = self._active_session()
        cancel_trade(session, self.alice_sheet)
        with self.assertRaises(TradeAlreadyResolved):
            cancel_trade(session, self.bob_sheet)

    def test_cancel_by_non_party_rejected(self) -> None:
        session = self._active_session()
        carol_sheet = CharacterSheetFactory()
        with self.assertRaises(NotATradeParty):
            cancel_trade(session, carol_sheet)
