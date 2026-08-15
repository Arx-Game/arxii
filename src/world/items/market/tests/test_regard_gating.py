"""Standing-based service gating (#2995): regard shifts price, gates access,
and refuses service outright — for persona-bearing NPC sellers only.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from evennia_extensions.models import PlayerData
from world.areas.factories import AreaFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.currency.services import get_or_create_purse, transfer
from world.items.factories import ItemTemplateFactory
from world.items.market.constants import REGARD_REFUSAL_FLOOR
from world.items.market.models import CraftingServiceOffer, MarketSale, MarketSquare, MarketStall
from world.items.market.services import (
    MarketServiceError,
    _regard_adjusted_price,
    purchase_stock,
)
from world.npc_services.factories import NpcRegardFactory
from world.roster.factories import RosterEntryFactory, RosterFactory, RosterTenureFactory
from world.scenes.factories import PersonaFactory


def _persona(name: str = "Buyer", gold: int = 0):
    character = CharacterFactory(db_key=name)
    sheet = CharacterSheetFactory(character=character)
    if gold:
        transfer(amount=gold, reason="seed", to_purse=get_or_create_purse(sheet))
    return sheet.primary_persona


def _square():
    area = AreaFactory(level=20)
    return MarketSquare.objects.create(name="Test Square", area=area)


class PriceBandWalkTests(TestCase):
    """Pure band-walk math — every boundary edge, no DB rows needed."""

    def test_band_boundaries(self) -> None:
        cases = {
            -1000: 150,
            -500: 150,
            -201: 150,
            -200: 115,
            -1: 115,
            0: 100,
            199: 100,
            200: 90,
            499: 90,
            500: 75,
            1000: 75,
        }
        for regard, expected_pct in cases.items():
            with self.subTest(regard=regard):
                self.assertEqual(_regard_adjusted_price(100, regard), expected_pct)


class RegardGatingStockTests(TestCase):
    """purchase_stock's regard gate + adjusted price (StockListing path)."""

    def setUp(self) -> None:
        self.buyer = _persona("Buyer", gold=10_000)
        self.shopkeeper = PersonaFactory()
        self.stall = MarketStall.objects.create(
            square=_square(), name="Attended Stall", shopkeeper_persona=self.shopkeeper
        )
        self.template = ItemTemplateFactory(name="Reserved Iron")

    def _listing(self, price=100, min_regard=None):
        return self.stall.stock_listings.create(
            template=self.template, price=price, min_regard=min_regard
        )

    def test_anonymous_stall_is_unaffected(self) -> None:
        """Both null (no shopkeeper) -> base price, no gate — the regression guard."""
        anon_stall = MarketStall.objects.create(square=self.stall.square, name="Anon Stall")
        listing = anon_stall.stock_listings.create(template=self.template, price=100)
        # Even a hostile regard row against some other holder is irrelevant here —
        # there's no shopkeeper_persona to read it from at all.
        instance, price = purchase_stock(listing=listing, buyer=self.buyer)
        self.assertEqual(price, 100)
        self.assertIsNotNone(instance.pk)

    def test_neutral_regard_charges_base_price(self) -> None:
        listing = self._listing(price=200)
        _instance, price = purchase_stock(listing=listing, buyer=self.buyer)
        self.assertEqual(price, 200)
        self.assertEqual(MarketSale.objects.get().price, 200)

    def test_favorable_regard_discounts_price(self) -> None:
        NpcRegardFactory(holder_persona=self.shopkeeper, target_persona=self.buyer, value=500)
        listing = self._listing(price=200)
        _instance, price = purchase_stock(listing=listing, buyer=self.buyer)
        self.assertEqual(price, 150)  # 75% band

    def test_hostile_regard_surcharges_price(self) -> None:
        NpcRegardFactory(holder_persona=self.shopkeeper, target_persona=self.buyer, value=-300)
        listing = self._listing(price=200)
        _instance, price = purchase_stock(listing=listing, buyer=self.buyer)
        self.assertEqual(price, 230)  # 115% band

    def test_refusal_floor_blocks_purchase_at_and_below(self) -> None:
        NpcRegardFactory(
            holder_persona=self.shopkeeper,
            target_persona=self.buyer,
            value=REGARD_REFUSAL_FLOOR,
        )
        listing = self._listing(price=200)
        with self.assertRaises(MarketServiceError):
            purchase_stock(listing=listing, buyer=self.buyer)

    def test_just_above_refusal_floor_is_allowed(self) -> None:
        NpcRegardFactory(
            holder_persona=self.shopkeeper,
            target_persona=self.buyer,
            value=REGARD_REFUSAL_FLOOR + 1,
        )
        listing = self._listing(price=200)
        _instance, price = purchase_stock(listing=listing, buyer=self.buyer)
        self.assertEqual(price, 300)  # still within the 150% band

    def test_reserved_stock_min_regard_gates_purchase(self) -> None:
        listing = self._listing(price=100, min_regard=100)
        NpcRegardFactory(holder_persona=self.shopkeeper, target_persona=self.buyer, value=0)
        with self.assertRaises(MarketServiceError):
            purchase_stock(listing=listing, buyer=self.buyer)

    def test_reserved_stock_purchasable_once_earned(self) -> None:
        listing = self._listing(price=100, min_regard=100)
        NpcRegardFactory(holder_persona=self.shopkeeper, target_persona=self.buyer, value=100)
        _instance, price = purchase_stock(listing=listing, buyer=self.buyer)
        self.assertEqual(price, 100)


class ModelValidationTests(TestCase):
    def test_stall_rejects_owner_and_shopkeeper_both_set(self) -> None:
        owner = _persona("Owner")
        shopkeeper = PersonaFactory()
        stall = MarketStall(
            square=_square(),
            name="Conflicted Stall",
            owner_persona=owner,
            shopkeeper_persona=shopkeeper,
        )
        with self.assertRaises(ValidationError):
            stall.full_clean()

    def test_min_regard_requires_a_shopkeeper(self) -> None:
        stall = MarketStall.objects.create(square=_square(), name="Anon Stall 2")
        template = ItemTemplateFactory(name="Ungated Iron")
        listing = stall.stock_listings.model(stall=stall, template=template, price=1, min_regard=1)
        with self.assertRaises(ValidationError):
            listing.full_clean()


class WareListingUnaffectedTests(TestCase):
    """WareListing/purchase_ware never reads regard at all (#2066 PC-to-PC path)."""

    def test_ware_purchase_never_touches_regard(self) -> None:
        from world.items.market.services import list_ware, purchase_ware
        from world.items.models import ItemInstance

        crafter = _persona("Crafter")
        buyer = _persona("Buyer", gold=5000)
        stall = MarketStall.objects.create(square=_square(), name="PC Stall", owner_persona=crafter)
        template = ItemTemplateFactory(name="Unfinished Plate")
        instance = ItemInstance.objects.create(
            template=template,
            holder_character_sheet=crafter.character_sheet,
            crafter_character_sheet=crafter.character_sheet,
        )
        listing = list_ware(stall=stall, seller=crafter, item_instance=instance, price=500)
        finishing_pass = purchase_ware(listing=listing, buyer=buyer)
        self.assertIsNotNone(finishing_pass.pk)
        self.assertEqual(MarketSale.objects.get().price, 500)


def _played_persona(*, account):
    """A primary persona whose character has an active roster tenure for account."""
    sheet = CharacterSheetFactory()
    RosterEntryFactory(character_sheet=sheet, roster=RosterFactory())
    player_data, _ = PlayerData.objects.get_or_create(account=account)
    RosterTenureFactory(player_data=player_data, roster_entry=sheet.roster_entry)
    return sheet.primary_persona


class ServiceOfferBrowseGatingTests(TestCase):
    """Regard-gated offer visibility on /api/items/service-offers/ (#2995)."""

    def setUp(self) -> None:
        self.client = APIClient()
        self.account = AccountFactory()
        self.client.force_authenticate(user=self.account)
        self.viewer = _played_persona(account=self.account)
        self.crafter = PersonaFactory()
        from evennia_extensions.factories import RoomProfileFactory

        self.shop_room = RoomProfileFactory()
        self.offer = CraftingServiceOffer.objects.create(
            crafter_persona=self.crafter,
            recipe_kind="facet_attach",
            shop_room=self.shop_room,
            fee=100,
            min_regard=100,
        )

    def test_gated_offer_hidden_below_threshold(self) -> None:
        NpcRegardFactory(holder_persona=self.crafter, target_persona=self.viewer, value=0)
        response = self.client.get("/api/items/service-offers/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [row["id"] for row in response.data]
        self.assertNotIn(self.offer.pk, ids)

    def test_gated_offer_visible_once_earned(self) -> None:
        NpcRegardFactory(holder_persona=self.crafter, target_persona=self.viewer, value=100)
        response = self.client.get("/api/items/service-offers/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [row["id"] for row in response.data]
        self.assertIn(self.offer.pk, ids)
        # Base fee only — no personalized price on browse (Decision 4).
        row = next(r for r in response.data if r["id"] == self.offer.pk)
        self.assertEqual(row["fee"], 100)
