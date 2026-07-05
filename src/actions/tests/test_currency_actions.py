"""Tests for the #1909 physical-currency actions: withdraw/deposit/give_coins/steal/secure."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from actions.definitions.currency import DepositCoinsAction, GiveCoinsAction, WithdrawCoinsAction
from actions.definitions.items import SetContainerPolicyAction, StealAction
from actions.prerequisites import CanStealPrerequisite
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.currency.constants import Denomination
from world.currency.models import CurrencyInstrumentDetails
from world.currency.services import get_or_create_purse, mint_loose_cache, transfer
from world.items.constants import ContainerAccessPolicy
from world.items.exceptions import NotInPossession, RecipientNotAdjacent, TheftNotPermitted
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.models import ItemInstance, OwnershipEvent


class WithdrawCoinsActionTests(TestCase):
    def _actor_with_balance(self, amount: int) -> tuple:
        room = ObjectDBFactory(db_key="Room", db_typeclass_path="typeclasses.rooms.Room")
        actor = CharacterFactory(db_key="WithdrawAlice", location=room)
        sheet = CharacterSheetFactory(character=actor)
        purse = get_or_create_purse(sheet)
        transfer(amount=amount, reason="seed", to_purse=purse)
        return room, actor, sheet, purse

    def test_withdraw_mints_loose_cache_and_debits_purse(self) -> None:
        room, actor, sheet, purse = self._actor_with_balance(1_000)

        action = WithdrawCoinsAction()
        with patch.object(room, "msg_contents"):
            result = action.run(actor, amount=350)

        assert result.success is True
        purse.refresh_from_db()
        assert purse.balance == 650
        instance = ItemInstance.objects.get(holder_character_sheet=sheet)
        details = CurrencyInstrumentDetails.objects.get(item_instance=instance)
        assert details.denomination == Denomination.LOOSE
        assert details.face_value == 350

    def test_withdraw_zero_or_missing_amount_fails(self) -> None:
        _room, actor, _sheet, _purse = self._actor_with_balance(1_000)
        action = WithdrawCoinsAction()

        result = action.run(actor)
        assert result.success is False
        assert result.message == "Withdraw how much?"

        result = action.run(actor, amount=0)
        assert result.success is False

    def test_withdraw_insufficient_funds_surfaces_message(self) -> None:
        _room, actor, _sheet, _purse = self._actor_with_balance(10)
        action = WithdrawCoinsAction()
        result = action.run(actor, amount=999)
        assert result.success is False
        assert "Insufficient funds" in result.message


class DepositCoinsActionTests(TestCase):
    def _actor_with_cache(self, amount: int) -> tuple:
        room = ObjectDBFactory(db_key="Room", db_typeclass_path="typeclasses.rooms.Room")
        actor = CharacterFactory(db_key="DepositAlice", location=room)
        sheet = CharacterSheetFactory(character=actor)
        purse = get_or_create_purse(sheet)
        transfer(amount=1_000, reason="seed", to_purse=purse)
        instance = mint_loose_cache(amount=amount, holder_sheet=sheet, from_purse=purse)
        # mint_loose_cache is a ledger-level service and does not spawn a
        # physical game_object (same gap as grant_touchstone_item_to_character
        # / building permits elsewhere in this codebase) — wire one here so
        # DepositCoinsAction has an ObjectDB target to resolve, same as it
        # would get from a caller's ``deposit <item>`` search in practice
        # once that materialization gap is addressed.
        game_obj = ObjectDBFactory(db_key="LooseCoinCache", location=actor)
        instance.game_object = game_obj
        instance.save(update_fields=["game_object"])
        return room, actor, sheet, purse, instance

    def test_deposit_redeems_instrument_and_credits_purse(self) -> None:
        room, actor, _sheet, purse, instance = self._actor_with_cache(350)
        purse.refresh_from_db()
        starting_balance = purse.balance

        action = DepositCoinsAction()
        with patch.object(room, "msg_contents"):
            result = action.run(actor, target=instance.game_object)

        assert result.success is True
        purse.refresh_from_db()
        assert purse.balance == starting_balance + 350
        assert not CurrencyInstrumentDetails.objects.filter(pk=instance.pk).exists()

    def test_deposit_missing_target_fails(self) -> None:
        _room, actor, _sheet, _purse, _instance = self._actor_with_cache(100)
        result = DepositCoinsAction().run(actor)
        assert result.success is False
        assert result.message == "Deposit what?"

    def test_deposit_non_coin_item_fails(self) -> None:
        _room, actor, _sheet, _purse, _instance = self._actor_with_cache(100)
        item_obj = ObjectDBFactory(db_key="NotACoin", location=actor)
        ItemInstanceFactory(template=ItemTemplateFactory(name="Rock"), game_object=item_obj)

        result = DepositCoinsAction().run(actor, target=item_obj)
        assert result.success is False
        assert result.message == "That isn't your coin."

    def test_deposit_someone_elses_coin_fails(self) -> None:
        _room, _actor, _sheet, _purse, instance = self._actor_with_cache(100)
        other = CharacterFactory(db_key="DepositOther")
        CharacterSheetFactory(character=other)

        result = DepositCoinsAction().run(other, target=instance.game_object)
        assert result.success is False
        assert result.message == "That isn't your coin."


class GiveCoinsActionTests(TestCase):
    def _two_characters(self, *, same_room: bool = True) -> tuple:
        room = ObjectDBFactory(db_key="Room", db_typeclass_path="typeclasses.rooms.Room")
        other_room = ObjectDBFactory(db_key="OtherRoom", db_typeclass_path="typeclasses.rooms.Room")
        actor = CharacterFactory(db_key="GiveCoinsAlice", location=room)
        recipient = CharacterFactory(
            db_key="GiveCoinsBob", location=room if same_room else other_room
        )
        actor_sheet = CharacterSheetFactory(character=actor)
        recipient_sheet = CharacterSheetFactory(character=recipient)
        actor_purse = get_or_create_purse(actor_sheet)
        transfer(amount=1_000, reason="seed", to_purse=actor_purse)
        return room, actor, recipient, actor_purse, get_or_create_purse(recipient_sheet)

    def test_give_coins_transfers_between_colocated_purses(self) -> None:
        room, actor, recipient, actor_purse, recipient_purse = self._two_characters()

        action = GiveCoinsAction()
        with patch.object(room, "msg_contents"):
            result = action.run(actor, recipient=recipient, amount=250)

        assert result.success is True
        actor_purse.refresh_from_db()
        recipient_purse.refresh_from_db()
        assert actor_purse.balance == 750
        assert recipient_purse.balance == 250

    def test_give_coins_not_adjacent_fails(self) -> None:
        _room, actor, recipient, _actor_purse, _recipient_purse = self._two_characters(
            same_room=False
        )

        result = GiveCoinsAction().run(actor, recipient=recipient, amount=100)
        assert result.success is False
        assert result.message == RecipientNotAdjacent.user_message

    def test_give_coins_insufficient_funds_fails(self) -> None:
        _room, actor, recipient, _actor_purse, _recipient_purse = self._two_characters()
        result = GiveCoinsAction().run(actor, recipient=recipient, amount=999_999)
        assert result.success is False
        assert "Insufficient funds" in result.message

    def test_give_coins_missing_amount_fails(self) -> None:
        _room, actor, recipient, _actor_purse, _recipient_purse = self._two_characters()
        result = GiveCoinsAction().run(actor, recipient=recipient)
        assert result.success is False
        assert result.message == "Give how much to whom?"


class StealActionTests(TestCase):
    def _scene(self) -> tuple:
        room = ObjectDBFactory(db_key="Room", db_typeclass_path="typeclasses.rooms.Room")
        thief = CharacterFactory(db_key="Thief", location=room)
        CharacterSheetFactory(character=thief)
        owner = CharacterFactory(db_key="Owner", location=room)
        owner_sheet = CharacterSheetFactory(character=owner)
        item_obj = ObjectDBFactory(db_key="OwnedItem", location=room)
        instance = ItemInstanceFactory(
            template=ItemTemplateFactory(name="OwnedThing"),
            game_object=item_obj,
            holder_character_sheet=owner_sheet,
        )
        return room, thief, owner, owner_sheet, item_obj, instance

    def test_steal_npc_owned_item_succeeds(self) -> None:
        # Owner has no active RosterTenure (NPC-like) -> steal_permitted() is True.
        room, thief, _owner, _owner_sheet, item_obj, instance = self._scene()

        action = StealAction()
        with patch.object(room, "msg_contents"):
            result = action.run(thief, target=item_obj)

        assert result.success is True
        instance.refresh_from_db()
        assert instance.holder_character_sheet == thief.sheet_data
        assert OwnershipEvent.objects.filter(item_instance=instance, event_type="stolen").exists()

    def test_steal_missing_target_fails(self) -> None:
        _room, thief, _owner, _owner_sheet, _item_obj, _instance = self._scene()
        result = StealAction().run(thief)
        assert result.success is False
        assert result.message == "Steal what?"

    def test_can_steal_prerequisite_blocks_when_not_permitted(self) -> None:
        """A player-owned, actively-tenured item defaults to consent-denied (ALLOWLIST)."""
        from world.roster.factories import RosterEntryFactory, RosterTenureFactory

        _room, thief, _owner, owner_sheet, item_obj, _instance = self._scene()
        entry = RosterEntryFactory(character_sheet=owner_sheet)
        RosterTenureFactory(roster_entry=entry, end_date=None)

        met, reason = CanStealPrerequisite().is_met(
            thief, target=None, context={"kwargs": {"target": item_obj}}
        )
        assert met is False
        assert reason == TheftNotPermitted.user_message


class SetContainerPolicyActionTests(TestCase):
    def _container(self) -> tuple:
        room = ObjectDBFactory(db_key="Room", db_typeclass_path="typeclasses.rooms.Room")
        owner = CharacterFactory(db_key="ContainerOwner", location=room)
        owner_sheet = CharacterSheetFactory(character=owner)
        container_obj = ObjectDBFactory(db_key="Chest", location=owner)
        container = ItemInstanceFactory(
            template=ItemTemplateFactory(name="Chest", is_container=True),
            game_object=container_obj,
            holder_character_sheet=owner_sheet,
        )
        return room, owner, owner_sheet, container_obj, container

    def test_owner_sets_policy(self) -> None:
        room, owner, _sheet, container_obj, container = self._container()

        action = SetContainerPolicyAction()
        with patch.object(room, "msg_contents"):
            result = action.run(owner, target=container_obj, policy="owner_only")

        assert result.success is True
        container.refresh_from_db()
        assert container.access_policy == ContainerAccessPolicy.OWNER_ONLY

    def test_non_owner_denied(self) -> None:
        room, _owner, _sheet, container_obj, _container = self._container()
        other = CharacterFactory(db_key="NotOwner", location=room)
        CharacterSheetFactory(character=other)

        result = SetContainerPolicyAction().run(other, target=container_obj, policy="open")
        assert result.success is False
        assert result.message == NotInPossession.user_message

    def test_invalid_policy_rejected(self) -> None:
        _room, owner, _sheet, container_obj, _container = self._container()
        result = SetContainerPolicyAction().run(owner, target=container_obj, policy="bogus")
        assert result.success is False
        assert result.message == "That's not a valid access policy."

    def test_missing_target_fails(self) -> None:
        _room, owner, _sheet, _container_obj, _container = self._container()
        result = SetContainerPolicyAction().run(owner, policy="open")
        assert result.success is False
