"""Tests for the player<->player negotiated trade actions (#2990)."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from actions.definitions.trade import (
    AcceptTradeAction,
    CancelTradeAction,
    ConfirmTradeAction,
    ProposeTradeAction,
    SetTradeCoinAction,
    StageTradeItemAction,
    UnstageTradeItemAction,
)
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.currency.services import get_or_create_purse, transfer
from world.items.factories import ItemInstanceFactory
from world.items.trade.models import TradeSession


class TradeActionsTestBase(TestCase):
    def setUp(self) -> None:
        self.room = ObjectDBFactory(
            db_key="TradeActionRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.alice = CharacterFactory(db_key="TradeActionAlice", location=self.room)
        self.alice_sheet = CharacterSheetFactory(character=self.alice)
        self.bob = CharacterFactory(db_key="TradeActionBob", location=self.room)
        self.bob_sheet = CharacterSheetFactory(character=self.bob)

    def _held_item(self, character, sheet, key: str = "Trinket"):
        obj = ObjectDBFactory(db_key=key, location=character)
        return ItemInstanceFactory(game_object=obj, holder_character_sheet=sheet)


class TradeActionHappyPathTests(TradeActionsTestBase):
    def test_full_round_trip_completes_the_trade(self) -> None:
        alice_item = self._held_item(self.alice, self.alice_sheet, key="AliceGem")
        bob_item = self._held_item(self.bob, self.bob_sheet, key="BobCoin")

        with patch.object(self.room, "msg_contents"):
            propose_result = ProposeTradeAction().run(self.alice, target=self.bob)
            assert propose_result.success is True
            session_id = propose_result.data["session_id"]

            accept_result = AcceptTradeAction().run(self.bob, session_id=session_id)
            assert accept_result.success is True

        stage_alice = StageTradeItemAction().run(
            self.alice, session_id=session_id, target=alice_item.game_object
        )
        assert stage_alice.success is True

        stage_bob = StageTradeItemAction().run(
            self.bob, session_id=session_id, target=bob_item.game_object
        )
        assert stage_bob.success is True

        confirm_alice = ConfirmTradeAction().run(self.alice, session_id=session_id)
        assert confirm_alice.success is True
        assert confirm_alice.data["completed"] is False

        with patch.object(self.room, "msg_contents"):
            confirm_bob = ConfirmTradeAction().run(self.bob, session_id=session_id)
        assert confirm_bob.success is True
        assert confirm_bob.data["completed"] is True

        alice_item.refresh_from_db()
        bob_item.refresh_from_db()
        assert alice_item.holder_character_sheet_id == self.bob_sheet.pk
        assert bob_item.holder_character_sheet_id == self.alice_sheet.pk

        session = TradeSession.objects.get(pk=session_id)
        assert session.status == TradeSession.Status.COMPLETED

    def test_unstage_rejects_a_non_owner(self) -> None:
        alice_item = self._held_item(self.alice, self.alice_sheet)
        with patch.object(self.room, "msg_contents"):
            session_id = ProposeTradeAction().run(self.alice, target=self.bob).data["session_id"]
            AcceptTradeAction().run(self.bob, session_id=session_id)

        stake_result = StageTradeItemAction().run(
            self.alice, session_id=session_id, target=alice_item.game_object
        )
        stake_id = stake_result.data["stake_id"]

        result = UnstageTradeItemAction().run(self.bob, stake_id=stake_id)
        assert result.success is False

    def test_set_coin_over_balance_fails_with_message(self) -> None:
        with patch.object(self.room, "msg_contents"):
            session_id = ProposeTradeAction().run(self.alice, target=self.bob).data["session_id"]
            AcceptTradeAction().run(self.bob, session_id=session_id)

        transfer(amount=10, reason="seed", to_purse=get_or_create_purse(self.alice_sheet))
        result = SetTradeCoinAction().run(self.alice, session_id=session_id, amount=100)
        assert result.success is False

    def test_cancel_trade_closes_the_session(self) -> None:
        with patch.object(self.room, "msg_contents"):
            session_id = ProposeTradeAction().run(self.alice, target=self.bob).data["session_id"]
            AcceptTradeAction().run(self.bob, session_id=session_id)
            result = CancelTradeAction().run(self.bob, session_id=session_id)
        assert result.success is True

        session = TradeSession.objects.get(pk=session_id)
        assert session.status == TradeSession.Status.CANCELLED

    def test_propose_trade_with_self_fails(self) -> None:
        result = ProposeTradeAction().run(self.alice, target=self.alice)
        assert result.success is False
