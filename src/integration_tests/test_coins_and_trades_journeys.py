"""Journeys for the actions ledger (#3657, tranche 6): coins in hand and a trade
across the table. Each types what a player types or sends what the web client
sends, and asserts what the player was told and what the ledger holds."""

from __future__ import annotations

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from integration_tests.harness import JourneyCase
from world.character_sheets.factories import CharacterSheetFactory
from world.currency.models import CurrencyInstrumentDetails
from world.currency.services import get_or_create_purse, transfer
from world.items.constants import ContainerAccessPolicy
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.models import ItemInstance, OwnershipEvent
from world.items.trade.models import TradeSession


def sheet_of(character):
    return character.sheet_data


def give_coppers(character, amount: int) -> None:
    transfer(
        amount=amount, reason="journey seed", to_purse=get_or_create_purse(sheet_of(character))
    )


def purse_balance(character) -> int:
    purse = get_or_create_purse(sheet_of(character))
    purse.refresh_from_db()
    return purse.balance


def held_item(character, name: str, **template_fields):
    """An item in *character*'s hands: a game object in their inventory and a row they hold."""
    obj = ObjectDBFactory(db_key=name, location=character)
    return ItemInstanceFactory(
        template=ItemTemplateFactory(name=name, **template_fields),
        game_object=obj,
        holder_character_sheet=sheet_of(character),
    )


def holder_of(item: ItemInstance):
    return ItemInstance.objects.filter(pk=item.pk).values_list("holder_character_sheet_id").get()[0]


class CoinsInHand(JourneyCase):
    """Ysmay turns purse money into coins she can carry, hand over, or lose."""

    def setUp(self) -> None:
        super().setUp()
        self.taproom = self.make_room("The Taproom")
        self.ysmay = self.make_player("Ysmay", room=self.taproom)
        self.hobb = self.make_player("Hobb", room=self.taproom)
        self.watch(self.hobb)

    def test_she_pulls_coin_from_her_purse_and_puts_it_back(self) -> None:
        give_coppers(self.ysmay, 1000)
        told = self.telnet(self.ysmay, "withdraw coins 3g 5s")
        self.assertIn("You withdraw 3g 5s in loose coins.", told)
        self.assertTold(self.hobb, "Ysmay withdraws 3g 5s in loose coins.")
        self.assertEqual(purse_balance(self.ysmay), 650)
        cache = ItemInstance.objects.get(holder_character_sheet=sheet_of(self.ysmay))
        self.assertEqual(cache.currency_instrument.face_value, 350)
        self.assertEqual(cache.game_object.location, self.ysmay)

        told = self.telnet(self.ysmay, f"deposit {cache.game_object.key}")
        self.assertIn("You deposit coins worth 3g 5s.", told)
        self.assertEqual(purse_balance(self.ysmay), 1000)
        self.assertFalse(CurrencyInstrumentDetails.objects.filter(pk=cache.pk).exists())

    def test_the_purse_and_the_coin_are_checked(self) -> None:
        give_coppers(self.ysmay, 10)
        usage = "Usage: withdraw coins <amount> (e.g. 'withdraw coins 3s 5c')"
        self.assertIn(usage, self.telnet(self.ysmay, "withdraw coins"))
        self.assertIn(usage, self.telnet(self.ysmay, "withdraw coins 0c"))
        self.assertIn("Insufficient funds", self.telnet(self.ysmay, "withdraw coins 9g"))
        self.assertEqual(purse_balance(self.ysmay), 10)

        self.assertIn("Deposit what?", self.telnet(self.ysmay, "deposit"))
        held_item(self.ysmay, "Rock")
        self.assertIn("That isn't your coin.", self.telnet(self.ysmay, "deposit Rock"))
        self.assertEqual(purse_balance(self.ysmay), 10)

    def test_coins_change_hands_in_the_room(self) -> None:
        give_coppers(self.ysmay, 1000)
        told = self.telnet(self.ysmay, "give 2g 5s to Hobb")
        self.assertIn("You give Hobb 2g 5s.", told)
        self.assertTold(self.hobb, "Ysmay gives Hobb 2g 5s.")
        self.assertEqual(purse_balance(self.ysmay), 750)
        self.assertEqual(purse_balance(self.hobb), 250)

        self.assertIn("Insufficient funds", self.telnet(self.ysmay, "give 9g to Hobb"))
        self.assertIn("Give what to whom?", self.telnet(self.ysmay, "give"))
        self.assertIn("Usage: give <item> to <recipient>", self.telnet(self.ysmay, "give to Hobb"))
        self.assertEqual(purse_balance(self.ysmay), 750)

        # The web hands the action the recipient directly; the room is still checked.
        result = self.web(self.ysmay, "give_coins", recipient=self.hobb)
        self.assertFalse(result.detail.success)
        self.assertIn("Give how much to whom?", result.detail.message)
        self.hobb.location = self.make_room("The Yard")
        result = self.web(self.ysmay, "give_coins", recipient=self.hobb, amount=100)
        self.assertFalse(result.detail.success)
        self.assertIn("They are not here to receive it.", result.detail.message)
        self.assertEqual(purse_balance(self.ysmay), 750)

    def test_a_thief_takes_from_a_stranger_and_not_from_a_player(self) -> None:
        # Dorran is nobody's character: no player holds his tenure, so the ownership
        # gate is the only thing in the way, and steal is the verb that passes it.
        dorran = CharacterFactory(db_key="Dorran", location=self.taproom)
        CharacterSheetFactory(character=dorran)
        locket = ItemInstanceFactory(
            template=ItemTemplateFactory(name="Silver Locket"),
            game_object=ObjectDBFactory(db_key="Silver Locket", location=self.taproom),
            holder_character_sheet=sheet_of(dorran),
        )
        told = self.telnet(self.ysmay, "steal Silver Locket")
        self.assertIn("You take Silver Locket.", told)
        self.assertTold(self.hobb, "Ysmay takes Silver Locket.")
        self.assertEqual(holder_of(locket), sheet_of(self.ysmay).pk)
        self.assertTrue(
            OwnershipEvent.objects.filter(item_instance=locket, event_type="stolen").exists()
        )

        # Hobb is a played character; his body-handling consent decides, and by default
        # it refuses.
        purse = ItemInstanceFactory(
            template=ItemTemplateFactory(name="Leather Purse"),
            game_object=ObjectDBFactory(db_key="Leather Purse", location=self.taproom),
            holder_character_sheet=sheet_of(self.hobb),
        )
        told = self.telnet(self.ysmay, "steal Leather Purse")
        self.assertIn("You can't bring yourself to take that.", told)
        self.assertEqual(holder_of(purse), sheet_of(self.hobb).pk)
        self.assertIn("Steal what?", self.telnet(self.ysmay, "steal"))

    def test_she_decides_who_may_open_her_chest(self) -> None:
        chest = held_item(self.ysmay, "Chest", is_container=True)
        usage = "Usage: secure <container>=<open|friends|owner_only>"
        self.assertIn(usage, self.telnet(self.ysmay, "secure"))
        self.assertIn(usage, self.telnet(self.ysmay, "secure Chest"))
        self.assertIn(
            "That's not a valid access policy.", self.telnet(self.ysmay, "secure Chest=bogus")
        )

        told = self.telnet(self.ysmay, "secure Chest=owner_only")
        self.assertIn("You set Chest's access policy.", told)
        chest.refresh_from_db()
        self.assertEqual(chest.access_policy, ContainerAccessPolicy.OWNER_ONLY)

        # Hobb cannot reach a chest in her pack, and the action refuses him outright.
        result = self.web(
            self.hobb, "set_container_policy", target=chest.game_object, policy="open"
        )
        self.assertFalse(result.detail.success)
        self.assertIn("You are not carrying that.", result.detail.message)
        chest.refresh_from_db()
        self.assertEqual(chest.access_policy, ContainerAccessPolicy.OWNER_ONLY)


class TradingAcrossTheTable(JourneyCase):
    """Ysmay and Hobb swap a brooch for a whistle; the trade has no telnet verb, the
    web client dispatches each step."""

    def setUp(self) -> None:
        super().setUp()
        self.steps = self.make_room("The Market Steps")
        self.ysmay = self.make_player("Ysmay", room=self.steps)
        self.hobb = self.make_player("Hobb", room=self.steps)
        self.watch(self.ysmay, self.hobb)
        self.brooch = held_item(self.ysmay, "Moth Brooch")
        self.whistle = held_item(self.hobb, "Tin Whistle")

    def propose(self):
        result = self.web(self.ysmay, "propose_trade", target=self.hobb.pk)
        self.assertTrue(result.detail.success, result.detail.message)
        return result.detail.data["session_id"]

    def test_a_trade_from_offer_to_handshake(self) -> None:
        session_id = self.propose()
        self.assertIn("offers to trade with", self.said(self.hobb))

        result = self.web(self.hobb, "accept_trade", session_id=session_id)
        self.assertTrue(result.detail.success, result.detail.message)
        self.assertIn("trade offer", self.said(self.ysmay))

        for character, item in ((self.ysmay, self.brooch), (self.hobb, self.whistle)):
            result = self.web(
                character, "stage_trade_item", session_id=session_id, target=item.game_object.pk
            )
            self.assertTrue(result.detail.success, result.detail.message)

        result = self.web(self.ysmay, "confirm_trade", session_id=session_id)
        self.assertTrue(result.detail.success, result.detail.message)
        self.assertIn("Confirmed. Waiting on the other side.", result.detail.message)
        self.assertFalse(result.detail.data["completed"])
        self.assertEqual(holder_of(self.brooch), sheet_of(self.ysmay).pk)

        result = self.web(self.hobb, "confirm_trade", session_id=session_id)
        self.assertTrue(result.detail.success, result.detail.message)
        self.assertTrue(result.detail.data["completed"])
        self.assertIn("complete a trade", self.said(self.ysmay))
        self.assertEqual(holder_of(self.brooch), sheet_of(self.hobb).pk)
        self.assertEqual(holder_of(self.whistle), sheet_of(self.ysmay).pk)
        self.assertEqual(
            TradeSession.objects.get(pk=session_id).status, TradeSession.Status.COMPLETED
        )

    def test_what_the_table_refuses(self) -> None:
        result = self.web(self.ysmay, "propose_trade")
        self.assertFalse(result.detail.success)
        self.assertIn("Propose a trade with whom?", result.detail.message)
        result = self.web(self.ysmay, "propose_trade", target=self.ysmay.pk)
        self.assertFalse(result.detail.success)
        self.assertIn("You cannot trade with yourself.", result.detail.message)

        session_id = self.propose()
        result = self.web(self.ysmay, "propose_trade", target=self.hobb.pk)
        self.assertFalse(result.detail.success)
        self.assertIn("You already have an open trade with them.", result.detail.message)
        result = self.web(
            self.hobb, "stage_trade_item", session_id=session_id, target=self.whistle.game_object.pk
        )
        self.assertFalse(result.detail.success)
        self.assertIn("That trade is not open for staging right now.", result.detail.message)
        result = self.web(self.hobb, "accept_trade", session_id=999999)
        self.assertFalse(result.detail.success)
        self.assertIn("That trade no longer exists.", result.detail.message)

        tam = self.make_player("Tam", room=self.steps)
        result = self.web(tam, "accept_trade", session_id=session_id)
        self.assertFalse(result.detail.success)
        self.assertIn("You are not part of that trade.", result.detail.message)
        result = self.web(self.hobb, "accept_trade", session_id=session_id)
        self.assertTrue(result.detail.success, result.detail.message)

        staged = self.web(
            self.ysmay, "stage_trade_item", session_id=session_id, target=self.brooch.game_object.pk
        )
        result = self.web(self.hobb, "unstage_trade_item", stake_id=staged.detail.data["stake_id"])
        self.assertFalse(result.detail.success)
        self.assertIn("That's not yours to unstage.", result.detail.message)
        result = self.web(self.hobb, "unstage_trade_item", stake_id=999999)
        self.assertFalse(result.detail.success)
        self.assertIn("That item is not on the table.", result.detail.message)

        give_coppers(self.ysmay, 10)
        result = self.web(self.ysmay, "set_trade_coin", session_id=session_id, amount=100)
        self.assertFalse(result.detail.success)
        self.assertIn("You don't have that much coin.", result.detail.message)
        result = self.web(self.ysmay, "set_trade_coin", session_id=session_id)
        self.assertFalse(result.detail.success)
        self.assertIn("Offer how much coin?", result.detail.message)

        result = self.web(self.hobb, "cancel_trade", session_id=session_id)
        self.assertTrue(result.detail.success, result.detail.message)
        self.assertIn("calls off the trade", self.said(self.ysmay))
        self.assertEqual(
            TradeSession.objects.get(pk=session_id).status, TradeSession.Status.CANCELLED
        )
        result = self.web(self.ysmay, "confirm_trade", session_id=session_id)
        self.assertFalse(result.detail.success)
        self.assertIn("That trade is not open for staging right now.", result.detail.message)
        self.assertEqual(holder_of(self.brooch), sheet_of(self.ysmay).pk)
