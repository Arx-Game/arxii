"""Market service tests (#2066): sinks, wares, finishing, provenance, cuts."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.areas.factories import AreaFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.currency.services import get_or_create_purse, transfer
from world.items.market.models import MarketSquare, MarketStall, StockListing
from world.items.market.services import (
    MarketServiceError,
    dual_provenance_line,
    finish_ware,
    list_ware,
    purchase_stock,
    purchase_ware,
)
from world.items.models import ItemInstance, ItemTemplate


def _persona(name: str, gold: int = 0):
    character = CharacterFactory(db_key=name)
    sheet = CharacterSheetFactory(character=character)
    if gold:
        transfer(amount=gold, reason="seed", to_purse=get_or_create_purse(sheet))
    return sheet.primary_persona


def _square():
    area = AreaFactory(level=20)
    return MarketSquare.objects.create(name="Test Market", area=area)


class StockTests(TestCase):
    def test_purchase_mints_instance_and_sinks_coin(self) -> None:
        buyer = _persona("Buyer", gold=1000)
        stall = MarketStall.objects.create(square=_square(), name="NPC Stall")
        template = ItemTemplate.objects.create(name="Iron Ingot T")
        listing = StockListing.objects.create(stall=stall, template=template, price=120)

        instance = purchase_stock(listing=listing, buyer=buyer)

        assert instance.holder_character_sheet_id == buyer.character_sheet_id
        purse = get_or_create_purse(buyer.character_sheet)
        purse.refresh_from_db()
        assert purse.balance == 880

    def test_unaffordable_purchase_refused(self) -> None:
        buyer = _persona("Poor", gold=10)
        stall = MarketStall.objects.create(square=_square(), name="NPC Stall")
        template = ItemTemplate.objects.create(name="Silk T")
        listing = StockListing.objects.create(stall=stall, template=template, price=500)
        with self.assertRaises(ValidationError):
            purchase_stock(listing=listing, buyer=buyer)


class WareTests(TestCase):
    def setUp(self) -> None:
        self.crafter = _persona("Crafter")
        self.buyer = _persona("Buyer", gold=5000)
        self.stall = MarketStall.objects.create(
            square=_square(), name="Crafter Stall", owner_persona=self.crafter
        )
        self.template = ItemTemplate.objects.create(name="Alaricite Plate Breastplate T")
        self.instance = ItemInstance.objects.create(
            template=self.template,
            holder_character_sheet=self.crafter.character_sheet,
            crafter_character_sheet=self.crafter.character_sheet,
        )

    def test_list_requires_crafter_held_unfinished(self) -> None:
        listing = list_ware(
            stall=self.stall, seller=self.crafter, item_instance=self.instance, price=800
        )
        assert listing.price == 800

        other = ItemInstance.objects.create(
            template=self.template,
            holder_character_sheet=self.crafter.character_sheet,
        )
        with self.assertRaises(MarketServiceError):
            list_ware(stall=self.stall, seller=self.crafter, item_instance=other, price=1)

        finished = ItemInstance.objects.create(
            template=self.template,
            holder_character_sheet=self.crafter.character_sheet,
            crafter_character_sheet=self.crafter.character_sheet,
            custom_name="Already Finished",
        )
        with self.assertRaises(MarketServiceError):
            list_ware(stall=self.stall, seller=self.crafter, item_instance=finished, price=1)

    def test_buy_and_finish_flow_with_dual_provenance(self) -> None:
        listing = list_ware(
            stall=self.stall, seller=self.crafter, item_instance=self.instance, price=800
        )
        finishing_pass = purchase_ware(listing=listing, buyer=self.buyer)

        self.instance.refresh_from_db()
        assert self.instance.holder_character_sheet_id == self.buyer.character_sheet_id
        crafter_purse = get_or_create_purse(self.crafter.character_sheet)
        crafter_purse.refresh_from_db()
        assert crafter_purse.balance == 800

        # Sold listings cannot sell twice.
        with self.assertRaises(MarketServiceError):
            purchase_ware(listing=listing, buyer=self.buyer)

        finished = finish_ware(
            finishing_pass=finishing_pass,
            actor=self.buyer,
            name="Dawnplate of the Unbroken Line",
            description="A breastplate described entirely in the buyer's own words.",
        )
        assert finished.custom_name == "Dawnplate of the Unbroken Line"
        assert finished.designer_character_sheet_id == self.buyer.character_sheet_id
        line = dual_provenance_line(finished)
        assert "Crafted by" in line
        assert "Designed by" in line

        # The pass is one-shot.
        with self.assertRaises(MarketServiceError):
            finish_ware(finishing_pass=finishing_pass, actor=self.buyer, name="X", description="")

    def test_only_pass_holder_may_finish(self) -> None:
        listing = list_ware(
            stall=self.stall, seller=self.crafter, item_instance=self.instance, price=100
        )
        finishing_pass = purchase_ware(listing=listing, buyer=self.buyer)
        interloper = _persona("Interloper")
        with self.assertRaises(MarketServiceError):
            finish_ware(
                finishing_pass=finishing_pass, actor=interloper, name="Nope", description=""
            )

    def test_self_finished_provenance_collapses(self) -> None:
        self.instance.custom_name = "Mine"
        self.instance.designer_character_sheet = self.crafter.character_sheet
        self.instance.save(update_fields=["custom_name", "designer_character_sheet"])
        line = dual_provenance_line(self.instance)
        assert line.startswith("Crafted and Designed by")


class HostCutTests(TestCase):
    def test_org_hosted_stall_routes_cut_to_treasury(self) -> None:
        from world.currency.models import OrganizationTreasury
        from world.societies.factories import OrganizationFactory

        crafter = _persona("Crafter2")
        buyer = _persona("Buyer2", gold=10_000)
        org = OrganizationFactory(name="Merchant House T")
        stall = MarketStall.objects.create(
            square=_square(),
            name="Hosted Stall",
            owner_persona=crafter,
            host_org=org,
            cut_percent=10,
        )
        template = ItemTemplate.objects.create(name="Cloak T")
        instance = ItemInstance.objects.create(
            template=template,
            holder_character_sheet=crafter.character_sheet,
            crafter_character_sheet=crafter.character_sheet,
        )
        listing = list_ware(stall=stall, seller=crafter, item_instance=instance, price=1000)
        purchase_ware(listing=listing, buyer=buyer)

        treasury = OrganizationTreasury.objects.get(organization=org)
        assert treasury.balance == 100
        crafter_purse = get_or_create_purse(crafter.character_sheet)
        crafter_purse.refresh_from_db()
        assert crafter_purse.balance == 900


class SeedTests(TestCase):
    def test_market_seed_idempotent(self) -> None:
        from world.seeds.market import MARKET_SQUARE_NAME, seed_market_demo

        seed_market_demo()
        first = StockListing.objects.count()
        seed_market_demo()
        assert StockListing.objects.count() == first
        assert MarketSquare.objects.filter(name=MARKET_SQUARE_NAME).exists()
