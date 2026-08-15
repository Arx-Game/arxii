"""PurchaseBuildingAction (#2991) — the action.run() dispatch seam over
world.buildings.services.purchase_building, plus PlaceFixtureAction's priced-
placement dispatch seam over the updated place_decoration."""

from __future__ import annotations

from django.test import TestCase, tag

from actions.registry import get_action
from actions.tests.room_test_helpers import character_in_room
from evennia_extensions.factories import RoomProfileFactory
from world.buildings.factories import BuildingListingFactory, DecorationKindFactory
from world.buildings.models import RoomDecoration
from world.currency.services import get_or_create_purse, transfer
from world.locations.constants import HolderType, LocationParentType
from world.locations.models import LocationOwnership


def _fund(sheet, amount: int) -> None:
    transfer(amount=amount, reason="seed", to_purse=get_or_create_purse(sheet))


def _own(room, sheet) -> None:
    """Direct LocationOwnership grant (no area set on ``room`` — no closure walk needed)."""
    LocationOwnership.objects.create(
        parent_type=LocationParentType.ROOM,
        room_profile=room,
        holder_type=HolderType.PERSONA,
        holder_persona=sheet.primary_persona,
    )


class PurchaseBuildingActionTests(TestCase):
    def test_no_such_listing_fails_cleanly(self) -> None:
        room = RoomProfileFactory()
        sheet, character = character_in_room(room)
        _fund(sheet, 10000)

        result = get_action("purchase_building").run(actor=character, listing_id=999999)

        self.assertFalse(result.success)
        self.assertEqual(result.message, "No such building listing.")

    def test_insufficient_funds_surfaces_service_error_message(self) -> None:
        room = RoomProfileFactory()
        sheet, character = character_in_room(room)
        _fund(sheet, 10)
        listing = BuildingListingFactory(price_coppers=5000)

        result = get_action("purchase_building").run(actor=character, listing_id=listing.pk)

        self.assertFalse(result.success)
        listing.refresh_from_db()
        self.assertTrue(listing.is_available)

    @tag("postgres")  # purchase_building -> transfer_ownership walks areas_areaclosure
    def test_successful_purchase_flips_listing_and_debits_purse(self) -> None:
        room = RoomProfileFactory()
        sheet, character = character_in_room(room)
        _fund(sheet, 10000)
        listing = BuildingListingFactory(price_coppers=5000)

        result = get_action("purchase_building").run(actor=character, listing_id=listing.pk)

        self.assertTrue(result.success, result.message)
        listing.refresh_from_db()
        self.assertFalse(listing.is_available)
        purse = get_or_create_purse(sheet)
        purse.refresh_from_db()
        self.assertEqual(purse.balance, 5000)


class PlaceFixtureActionPricingTests(TestCase):
    def test_priced_placement_charges_and_reports_cost(self) -> None:
        room = RoomProfileFactory()
        sheet, character = character_in_room(room)
        _own(room, sheet)
        _fund(sheet, 1000)
        DecorationKindFactory(name="Rug", amenity=50, cost_coppers=40)

        result = get_action("place_room_fixture").run(actor=character, kind="Rug")

        self.assertTrue(result.success, result.message)
        self.assertIn("-40c", result.message)
        purse = get_or_create_purse(sheet)
        purse.refresh_from_db()
        self.assertEqual(purse.balance, 960)

    def test_insufficient_funds_refuses_placement(self) -> None:
        room = RoomProfileFactory()
        sheet, character = character_in_room(room)
        _own(room, sheet)
        _fund(sheet, 10)
        DecorationKindFactory(name="Chandelier", amenity=200, cost_coppers=500)

        result = get_action("place_room_fixture").run(actor=character, kind="Chandelier")

        self.assertFalse(result.success)
        self.assertEqual(RoomDecoration.objects.count(), 0)
