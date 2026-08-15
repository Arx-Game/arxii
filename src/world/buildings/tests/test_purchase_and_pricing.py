"""Property purchase & decoration pricing economy tests (#2991).

Covers the three MVP surfaces: ``purchase_building`` (deed transfer + treasury sink),
priced ``place_decoration`` (flat coppers via ``transfer()``), and the crafted-furniture
quality → decor contribution mapping (the ratified amendment's seam over ADR-0192).
"""

from __future__ import annotations

from django.test import TestCase, tag

from evennia_extensions.factories import CharacterFactory, RoomProfileFactory
from world.buildings.factories import (
    BuildingFactory,
    BuildingListingFactory,
    DecorationKindFactory,
)
from world.buildings.models import RoomDecoration
from world.buildings.services import (
    BuildingPurchaseError,
    DecorationPlacementError,
    crafted_decoration_amenity,
    place_decoration,
    purchase_building,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.currency.services import get_or_create_purse, get_or_create_treasury, transfer
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory, QualityTierFactory
from world.locations.services import comfort_points, is_owner
from world.societies.factories import OrganizationFactory


def _persona(name: str, gold: int = 0):
    character = CharacterFactory(db_key=name)
    sheet = CharacterSheetFactory(character=character)
    if gold:
        transfer(amount=gold, reason="seed", to_purse=get_or_create_purse(sheet))
    return sheet.primary_persona


class PurchaseBuildingTests(TestCase):
    @tag("postgres")  # is_owner walks the areas_areaclosure materialized view
    def test_purchase_debits_purse_transfers_deed_and_marks_sold(self) -> None:
        buyer = _persona("Buyer", gold=10000)
        org = OrganizationFactory(name="Ward Office")
        listing = BuildingListingFactory(price_coppers=5000, organization=org)
        room = RoomProfileFactory(area=listing.building.area)

        purchase_building(persona=buyer, listing=listing)

        listing.refresh_from_db()
        assert listing.is_available is False
        assert listing.sold_to_persona_id == buyer.pk
        assert listing.sold_at is not None

        purse = get_or_create_purse(buyer.character_sheet)
        purse.refresh_from_db()
        assert purse.balance == 5000  # 10000 - 5000

        treasury = get_or_create_treasury(org)
        treasury.refresh_from_db()
        assert treasury.balance == 5000

        assert is_owner(buyer, room.objectdb)
        listing.building.refresh_from_db()
        assert listing.building.owner_persona_id == buyer.pk

    def test_purchase_falls_back_to_placeholder_treasury_when_unset(self) -> None:
        buyer = _persona("Buyer2", gold=1000)
        listing = BuildingListingFactory(price_coppers=500, organization=None)

        purchase_building(persona=buyer, listing=listing)

        purse = get_or_create_purse(buyer.character_sheet)
        purse.refresh_from_db()
        assert purse.balance == 500

    def test_insufficient_funds_refused_and_listing_unchanged(self) -> None:
        buyer = _persona("Poor", gold=10)
        listing = BuildingListingFactory(price_coppers=5000)

        with self.assertRaises(BuildingPurchaseError):
            purchase_building(persona=buyer, listing=listing)

        listing.refresh_from_db()
        assert listing.is_available is True
        assert listing.sold_to_persona_id is None
        purse = get_or_create_purse(buyer.character_sheet)
        purse.refresh_from_db()
        assert purse.balance == 10

    def test_already_sold_listing_refused(self) -> None:
        buyer = _persona("Buyer3", gold=10000)
        other_buyer = _persona("Buyer4", gold=10000)
        listing = BuildingListingFactory(price_coppers=1000)
        purchase_building(persona=buyer, listing=listing)

        with self.assertRaises(BuildingPurchaseError):
            purchase_building(persona=other_buyer, listing=listing)

        purse = get_or_create_purse(other_buyer.character_sheet)
        purse.refresh_from_db()
        assert purse.balance == 10000  # untouched


class PricedDecorationPlacementTests(TestCase):
    def _room(self):
        building = BuildingFactory()
        return RoomProfileFactory(area=building.area)

    def test_placement_charges_flat_cost(self) -> None:
        placer = _persona("Placer", gold=1000)
        profile = self._room()
        kind = DecorationKindFactory(name="Rug", amenity=100, cost_coppers=40)

        place_decoration(profile, kind, buyer_persona=placer)

        purse = get_or_create_purse(placer.character_sheet)
        purse.refresh_from_db()
        assert purse.balance == 960

    def test_free_kind_places_without_a_persona(self) -> None:
        profile = self._room()
        kind = DecorationKindFactory(name="Free Rug", amenity=50, cost_coppers=0)

        decoration = place_decoration(profile, kind)

        assert decoration.kind_id == kind.pk

    def test_priced_kind_without_persona_is_refused(self) -> None:
        profile = self._room()
        kind = DecorationKindFactory(name="Priced Rug", amenity=50, cost_coppers=40)

        with self.assertRaises(DecorationPlacementError):
            place_decoration(profile, kind)

        assert RoomDecoration.objects.count() == 0

    def test_insufficient_funds_refuses_placement(self) -> None:
        placer = _persona("BrokePlacer", gold=10)
        profile = self._room()
        kind = DecorationKindFactory(name="Expensive Rug", amenity=50, cost_coppers=40)

        with self.assertRaises(DecorationPlacementError):
            place_decoration(profile, kind, buyer_persona=placer)

        assert RoomDecoration.objects.count() == 0
        purse = get_or_create_purse(placer.character_sheet)
        purse.refresh_from_db()
        assert purse.balance == 10


class CraftedFurnitureQualityMappingTests(TestCase):
    """The #2991 amendment's seam: a crafted item's quality feeds decor amenity."""

    def test_crafted_decoration_amenity_scales_by_quality_multiplier(self) -> None:
        kind = DecorationKindFactory(name="Chair", amenity=100)
        fine = QualityTierFactory(name="Fine T", stat_multiplier="1.50")
        assert crafted_decoration_amenity(kind, fine) == 150

    def test_crafted_decoration_amenity_falls_back_to_base_when_no_quality(self) -> None:
        kind = DecorationKindFactory(name="Chair2", amenity=100)
        assert crafted_decoration_amenity(kind, None) == 100

    @tag("postgres")  # comfort_points walks the areas_areaclosure materialized view
    def test_placement_from_crafted_item_uses_quality_scaled_amenity(self) -> None:
        crafter = _persona("Crafter")
        profile = self._room()
        template = ItemTemplateFactory(name="Oak Chair T")
        kind = DecorationKindFactory(name="Oak Chair", amenity=100, crafted_item_template=template)
        masterwork = QualityTierFactory(name="Masterwork T", stat_multiplier="2.00")
        instance = ItemInstanceFactory(
            template=template,
            quality_tier=masterwork,
            holder_character_sheet=crafter.character_sheet,
        )

        decoration = place_decoration(profile, kind, buyer_persona=crafter, item_instance=instance)

        assert decoration.source_item_instance_id == instance.pk
        assert comfort_points(profile.objectdb) == 200  # 100 base * 2.00 multiplier

    def test_placement_requires_matching_template(self) -> None:
        crafter = _persona("Crafter2")
        profile = self._room()
        template = ItemTemplateFactory(name="Ash Table T")
        wrong_template = ItemTemplateFactory(name="Not A Table T")
        kind = DecorationKindFactory(name="Ash Table", crafted_item_template=template)
        instance = ItemInstanceFactory(
            template=wrong_template, holder_character_sheet=crafter.character_sheet
        )

        with self.assertRaises(DecorationPlacementError):
            place_decoration(profile, kind, buyer_persona=crafter, item_instance=instance)

    def test_placement_requires_holding_the_item(self) -> None:
        crafter = _persona("Crafter3")
        other = _persona("Other")
        profile = self._room()
        template = ItemTemplateFactory(name="Iron Sconce T")
        kind = DecorationKindFactory(name="Iron Sconce", crafted_item_template=template)
        instance = ItemInstanceFactory(
            template=template, holder_character_sheet=other.character_sheet
        )

        with self.assertRaises(DecorationPlacementError):
            place_decoration(profile, kind, buyer_persona=crafter, item_instance=instance)

    def test_crafted_kind_without_item_instance_is_refused(self) -> None:
        crafter = _persona("Crafter4")
        profile = self._room()
        template = ItemTemplateFactory(name="Standing Mirror T")
        kind = DecorationKindFactory(name="Standing Mirror", crafted_item_template=template)

        with self.assertRaises(DecorationPlacementError):
            place_decoration(profile, kind, buyer_persona=crafter)

    def test_an_item_cannot_be_placed_twice(self) -> None:
        crafter = _persona("Crafter5")
        profile_a = self._room()
        profile_b = self._room()
        template = ItemTemplateFactory(name="Fainting Couch T")
        kind = DecorationKindFactory(name="Fainting Couch", crafted_item_template=template)
        instance = ItemInstanceFactory(
            template=template, holder_character_sheet=crafter.character_sheet
        )
        place_decoration(profile_a, kind, buyer_persona=crafter, item_instance=instance)

        with self.assertRaises(DecorationPlacementError):
            place_decoration(profile_b, kind, buyer_persona=crafter, item_instance=instance)

    def _room(self):
        building = BuildingFactory()
        return RoomProfileFactory(area=building.area)
