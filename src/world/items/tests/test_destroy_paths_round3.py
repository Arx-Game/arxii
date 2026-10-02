"""Last soft-delete paths through the shared helper, and spills that strand nothing (#4099).

``recycle_item`` and ``redeem_favor_token`` hand-rolled the soft-delete (stamping
``destroyed_at`` but leaving the holder), so a recycled crafted piece could still be
listed and sold, and a redeemed Hare traded. ``_spill_contents`` used to drop a nested
pouch's contents out of the bag it sat in, and stranded contents when the container
was nowhere.
"""

from __future__ import annotations

from django.test import TestCase
from evennia import create_object

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.items.constants import BodyRegion, EquipmentLayer, OwnershipEventType
from world.items.exceptions import NotInPossession
from world.items.factories import EquippedItemFactory, ItemInstanceFactory, ItemTemplateFactory
from world.items.models import ItemInstance, OwnershipEvent
from world.items.services.usage import destroy_consumed_item_instance


def _obj(location=None):
    obj = create_object("typeclasses.objects.Object", key="thing", nohome=True)
    if location is not None:
        obj.location = location
    return obj


def _item(sheet, *, location=None, template=None, **fields) -> ItemInstance:
    return ItemInstanceFactory(
        template=template or ItemTemplateFactory(value=100),
        holder_character_sheet=sheet,
        game_object=_obj(location),
        **fields,
    )


def _put(content: ItemInstance, container: ItemInstance) -> None:
    content.contained_in = container
    content.save(update_fields=["contained_in"])
    content.game_object.location = container.game_object


def _with_history(item: ItemInstance, sheet) -> ItemInstance:
    OwnershipEvent.objects.create(
        item_instance=item, event_type=OwnershipEventType.GIVEN, to_character_sheet=sheet
    )
    return item


def _market(sheet):
    from world.areas.models import Area
    from world.items.market.models import MarketSquare, MarketStall

    square = MarketSquare.objects.create(
        name=f"Square {sheet.pk}", area=Area.objects.create(name=f"Ward {sheet.pk}", level=20)
    )
    return MarketStall.objects.create(square=square, name=f"Stall {sheet.pk}")


class RecycleUsesTheHelperTests(TestCase):
    def setUp(self) -> None:
        self.room = ObjectDBFactory(
            db_key="RecycleRoom", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.sheet = CharacterSheetFactory(character=CharacterFactory(location=self.room))
        self.piece = _with_history(
            _item(
                self.sheet,
                location=self.sheet.character,
                crafter_character_sheet=self.sheet,
            ),
            self.sheet,
        )

    def test_a_recycled_piece_is_held_by_nobody_and_cannot_be_listed(self) -> None:
        from world.items.market.services import MarketServiceError, list_ware
        from world.items.services.recycle import recycle_item

        recycle_item(item_instance=self.piece, actor_sheet=self.sheet)
        self.piece.refresh_from_db()
        self.assertIsNotNone(self.piece.destroyed_at)
        self.assertIsNone(self.piece.holder_character_sheet_id)
        with self.assertRaises(MarketServiceError):
            list_ware(
                stall=_market(self.sheet),
                seller=self.sheet.primary_persona,
                item_instance=self.piece,
                price=10,
            )

    def test_a_recycled_piece_cannot_be_staked_in_a_trade(self) -> None:
        from world.items.services.recycle import recycle_item
        from world.items.trade.services import accept_trade, propose_trade, stake_item

        other = CharacterSheetFactory(character=CharacterFactory(location=self.room))
        session = accept_trade(propose_trade(self.sheet, other), other)
        recycle_item(item_instance=self.piece, actor_sheet=self.sheet)
        with self.assertRaises(NotInPossession):
            stake_item(session, self.sheet, self.piece)

    def test_recycling_a_pouch_spills_its_contents(self) -> None:
        from world.items.services.recycle import recycle_item

        pouch = _item(
            self.sheet,
            location=self.sheet.character,
            template=ItemTemplateFactory(is_container=True),
        )
        coin = _item(self.sheet)
        _put(coin, pouch)
        recycle_item(item_instance=pouch, actor_sheet=self.sheet)
        coin.refresh_from_db()
        self.assertIsNone(coin.contained_in_id)
        self.assertEqual(coin.game_object.location, self.sheet.character)


class RedeemedHareTests(TestCase):
    def test_a_redeemed_hare_is_held_by_nobody_and_cannot_be_traded_or_listed(self) -> None:
        from world.currency.services import mint_favor_token, redeem_favor_token
        from world.items.market.services import MarketServiceError, list_ware
        from world.items.trade.services import accept_trade, propose_trade, stake_item
        from world.societies.factories import OrganizationFactory

        room = ObjectDBFactory(db_key="HareRoom", db_typeclass_path="typeclasses.rooms.Room")
        sheet = CharacterSheetFactory(character=CharacterFactory(location=room))
        other = CharacterSheetFactory(character=CharacterFactory(location=room))
        org = OrganizationFactory()
        token = mint_favor_token(org, sheet, provenance_note="Held the bridge")
        hare = token.item_instance
        hare.crafter_character_sheet = sheet
        hare.save(update_fields=["crafter_character_sheet"])
        session = accept_trade(propose_trade(sheet, other), other)

        redeem_favor_token(token, redeemer_org=org)

        hare.refresh_from_db()
        self.assertIsNone(hare.holder_character_sheet_id)
        with self.assertRaises(NotInPossession):
            stake_item(session, sheet, hare)
        with self.assertRaises(MarketServiceError):
            list_ware(
                stall=_market(sheet), seller=sheet.primary_persona, item_instance=hare, price=1
            )


class SpillTests(TestCase):
    def setUp(self) -> None:
        self.room = ObjectDBFactory(db_key="SpillRoom", db_typeclass_path="typeclasses.rooms.Room")
        self.sheet = CharacterSheetFactory(character=CharacterFactory(location=self.room))
        self.character = self.sheet.character
        self.box = ItemTemplateFactory(is_container=True)

    def _spill(self, container: ItemInstance) -> None:
        destroy_consumed_item_instance(container, note="Broken.")

    def test_a_chest_in_a_room_spills_into_the_room(self) -> None:
        chest = _item(None, location=self.room, template=self.box)
        coin = _item(self.sheet)
        _put(coin, chest)
        self._spill(chest)
        coin.refresh_from_db()
        self.assertIsNone(coin.contained_in_id)
        self.assertEqual(coin.game_object.location, self.room)
        self.assertEqual(coin.holder_character_sheet, self.sheet)

    def test_a_pouch_inside_a_bag_leaves_its_contents_in_the_bag(self) -> None:
        bag = _item(self.sheet, location=self.character, template=self.box)
        pouch = _with_history(_item(self.sheet, template=self.box), self.sheet)
        _put(pouch, bag)
        coin = _item(self.sheet)
        _put(coin, pouch)
        self._spill(pouch)
        coin.refresh_from_db()
        self.assertEqual(coin.contained_in, bag)
        self.assertEqual(coin.game_object.location, bag.game_object)

    def test_a_hard_deleted_containers_contents_land_with_the_carrier_not_home(self) -> None:
        home = ObjectDBFactory(db_key="Home", db_typeclass_path="typeclasses.rooms.Room")
        pouch = _item(self.sheet, location=self.character, template=self.box)
        coin = _item(self.sheet)
        coin.game_object.home = home
        coin.game_object.save()
        _put(coin, pouch)
        self._spill(pouch)
        self.assertFalse(ItemInstance.objects.filter(pk=pouch.pk).exists())
        coin.refresh_from_db()
        self.assertEqual(coin.game_object.location, self.character)

    def test_an_equipped_containers_contents_stay_with_the_wearer(self) -> None:
        pouch = _with_history(
            _item(self.sheet, location=self.character, template=self.box), self.sheet
        )
        EquippedItemFactory(
            character=self.sheet,
            item_instance=pouch,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        coin = _item(self.sheet)
        _put(coin, pouch)
        self._spill(pouch)
        coin.refresh_from_db()
        self.assertIsNone(coin.contained_in_id)
        self.assertEqual(coin.game_object.location, self.character)

    def test_contents_of_a_container_that_was_nowhere_go_to_the_former_holder(self) -> None:
        # Held, with a history (so it is soft-deleted, not deleted by Evennia), but its
        # game object is nowhere: the spill has no landing.
        pouch = _with_history(_item(self.sheet, template=self.box), self.sheet)
        coin = _item(self.sheet)
        _put(coin, pouch)
        self._spill(pouch)
        coin.refresh_from_db()
        self.assertEqual(coin.game_object.location, self.character)


class StaffViewsRefuseDestroyedItemsTests(TestCase):
    def test_gem_cut_quote_on_a_destroyed_item_is_a_clean_400(self) -> None:
        from decimal import Decimal

        from evennia.accounts.models import AccountDB
        from rest_framework.test import APIClient

        from world.items.factories import GemGradeFactory, GemInstanceDetailsFactory
        from world.items.gems.constants import GemAxis

        sheet = CharacterSheetFactory()
        item = _with_history(_item(sheet, location=sheet.character), sheet)
        GemInstanceDetailsFactory(
            item_instance=item,
            size_grade=GemGradeFactory(axis=GemAxis.SIZE, multiplier=Decimal("1.0")),
            purity_grade=GemGradeFactory(axis=GemAxis.PURITY, multiplier=Decimal("1.0")),
            cut_grade=GemGradeFactory(axis=GemAxis.CUT, multiplier=Decimal("1.0")),
        )
        destroy_consumed_item_instance(item, note="Broken.")
        staff = AccountDB.objects.create_superuser("round3staff", "r3@example.com", "pw-123456")
        client = APIClient()
        client.force_authenticate(staff)
        response = client.get(f"/api/items/gem-cuts/quote/?item_instance={item.pk}")
        self.assertEqual(response.status_code, 400)


class AdminLastHolderTests(TestCase):
    def test_admin_shows_the_last_holder_of_a_destroyed_item(self) -> None:
        from django.contrib import admin

        sheet = CharacterSheetFactory()
        item = _with_history(_item(sheet), sheet)
        destroy_consumed_item_instance(item, note="Broken.")
        model_admin = admin.site._registry[ItemInstance]
        self.assertIn("last_holder", model_admin.get_readonly_fields(None, item))
        self.assertEqual(model_admin.last_holder(item), str(sheet))
