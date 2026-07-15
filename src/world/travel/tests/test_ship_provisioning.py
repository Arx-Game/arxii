"""Tests for ship provisioning integration into advance_leg (#2217)."""

from django.test import TestCase

from world.travel.constants import TravelMode, VoyageStatus
from world.travel.models import Voyage, VoyageParticipant
from world.travel.services import VoyageError, advance_leg


class AdvanceLegProvisioningTests(TestCase):
    def setUp(self):
        from world.agriculture.models import FoodStockpile
        from world.agriculture.services.production import get_food_config
        from world.areas.factories import AreaFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.ships.factories import ShipDetailsFactory
        from world.societies.factories import (
            OrganizationFactory,
            OrganizationMembershipFactory,
        )
        from world.societies.houses.models import Domain
        from world.travel.factories import (
            TravelHubFactory,
            TravelMethodFactory,
            TravelRouteFactory,
        )

        self.sheet = CharacterSheetFactory()
        self.persona = self.sheet.primary_persona
        self.org = OrganizationFactory()
        OrganizationMembershipFactory(
            organization=self.org,
            persona=self.persona,
            rank=1,
        )
        self.domain = Domain.objects.create(
            area=AreaFactory(),
            name="TestDomain",
            owner_org=self.org,
            population=100,
        )
        self.stockpile = FoodStockpile.objects.create(domain=self.domain, stored=500)

        self.ship = ShipDetailsFactory(building__owner_persona=self.persona)

        self.origin_hub = TravelHubFactory(name="Port A", travel_modes=[TravelMode.SEA.value])
        self.mid_hub = TravelHubFactory(name="Port B", travel_modes=[TravelMode.SEA.value])
        self.dest_hub = TravelHubFactory(name="Port C", travel_modes=[TravelMode.SEA.value])
        TravelRouteFactory(
            origin_hub=self.origin_hub,
            destination_hub=self.mid_hub,
            distance=100,
            travel_mode=TravelMode.SEA,
        )
        TravelRouteFactory(
            origin_hub=self.mid_hub,
            destination_hub=self.dest_hub,
            distance=100,
            travel_mode=TravelMode.SEA,
        )
        self.travel_method = TravelMethodFactory(travel_mode=TravelMode.SEA)
        self.voyage = Voyage.objects.create(
            leader=self.persona,
            travel_method=self.travel_method,
            origin_hub=self.origin_hub,
            destination_hub=self.dest_hub,
            route_hubs=[
                self.origin_hub.pk,
                self.mid_hub.pk,
                self.dest_hub.pk,
            ],
            current_leg_index=0,
            status=VoyageStatus.IN_TRANSIT,
            ship=self.ship,
        )
        VoyageParticipant.objects.create(voyage=self.voyage, persona=self.persona)

        config = get_food_config()
        config.crew_food_per_leg = 5
        config.ship_provisioning_ap_surcharge = 50
        config.save()

    def test_full_provisions_normal_ap(self):
        """Well-stocked -> voyage advances, ratio 1.0, no AP surcharge."""
        advance_leg(self.voyage, self.persona)
        self.voyage.refresh_from_db()

        self.assertEqual(self.voyage.current_leg_index, 1)
        self.assertEqual(self.voyage.provisioning_ratio, 1.0)

    def test_zero_provisions_blocks_advance(self):
        """No stockpile -> advance_leg raises VoyageError."""
        self.stockpile.delete()

        with self.assertRaises(VoyageError):
            advance_leg(self.voyage, self.persona)

        self.voyage.refresh_from_db()
        self.assertEqual(self.voyage.current_leg_index, 0)

    def test_no_owner_blocks_advance(self):
        """Ship with no owner -> ratio 0.0, advance blocked."""
        self.ship.building.owner_persona = None
        self.ship.building.save()

        with self.assertRaises(VoyageError):
            advance_leg(self.voyage, self.persona)

    def test_land_voyage_unaffected(self):
        """Voyage with no ship -> ratio stays None, advances normally."""
        self.voyage.ship = None
        self.voyage.save()

        advance_leg(self.voyage, self.persona)
        self.voyage.refresh_from_db()

        self.assertEqual(self.voyage.current_leg_index, 1)
        self.assertIsNone(self.voyage.provisioning_ratio)

    def test_partial_provisions_ap_surcharge(self):
        """Partial food -> ratio < 1.0, AP surcharge applied, still advances."""
        # needed = crew_capacity(10) x crew_food_per_leg(5) = 50
        # available = 25 -> ratio = 0.5 -> surcharge = (1-0.5) x 50% = 25%
        self.stockpile.stored = 25
        self.stockpile.save()

        advance_leg(self.voyage, self.persona)
        self.voyage.refresh_from_db()

        self.assertEqual(self.voyage.current_leg_index, 1)
        self.assertAlmostEqual(self.voyage.provisioning_ratio, 0.5, places=2)
