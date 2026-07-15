"""Tests for ship crew provisioning per voyage leg (#2217)."""

from django.test import TestCase

from world.agriculture.models import FoodStockpile
from world.agriculture.services.production import get_food_config
from world.agriculture.services.provisioning import provision_ship_leg


class ProvisionShipLegTests(TestCase):
    def setUp(self):
        from world.areas.factories import AreaFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.ships.factories import ShipDetailsFactory
        from world.societies.factories import (
            OrganizationFactory,
            OrganizationMembershipFactory,
        )
        from world.societies.houses.models import Domain
        from world.travel.constants import TravelMode
        from world.travel.factories import (
            TravelHubFactory,
            TravelMethodFactory,
            TravelRouteFactory,
        )
        from world.travel.models import Voyage, VoyageParticipant

        self.sheet = CharacterSheetFactory()
        self.persona = self.sheet.primary_persona
        self.org = OrganizationFactory()
        OrganizationMembershipFactory(
            organization=self.org,
            persona=self.persona,
            rank=1,  # tier 1 = can_manage_ranks=True
        )
        self.domain = Domain.objects.create(
            area=AreaFactory(),
            name="TestDomain",
            owner_org=self.org,
            population=100,
        )
        self.stockpile = FoodStockpile.objects.create(domain=self.domain, stored=500)

        # Ship owned by this persona
        self.ship = ShipDetailsFactory(building__owner_persona=self.persona)

        # Voyage with this ship
        self.origin_hub = TravelHubFactory(name="Port A", travel_modes=[TravelMode.SEA.value])
        self.dest_hub = TravelHubFactory(name="Port B", travel_modes=[TravelMode.SEA.value])
        TravelRouteFactory(
            origin_hub=self.origin_hub,
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
            route_hubs=[self.origin_hub.pk, self.dest_hub.pk],
            current_leg_index=0,
            status="in_transit",
            ship=self.ship,
        )
        VoyageParticipant.objects.create(voyage=self.voyage, persona=self.persona)

        config = get_food_config()
        config.crew_food_per_leg = 5
        config.save()

    def test_full_provisioning_ratio_is_one(self):
        """Well-stocked stockpile -> ratio 1.0, food deducted."""
        ratio = provision_ship_leg(self.voyage)
        self.voyage.refresh_from_db()

        self.assertEqual(ratio, 1.0)
        self.assertEqual(self.voyage.provisioning_ratio, 1.0)
        # needed = crew_capacity(10) x crew_food_per_leg(5) = 50
        self.stockpile.refresh_from_db()
        self.assertEqual(self.stockpile.stored, 450)

    def test_partial_provisioning_ratio(self):
        """Insufficient food -> ratio < 1.0, stockpile drained to 0."""
        self.stockpile.stored = 25
        self.stockpile.save()

        ratio = provision_ship_leg(self.voyage)
        self.voyage.refresh_from_db()

        # needed = 50, available = 25, ratio = 0.5
        self.assertAlmostEqual(ratio, 0.5, places=2)
        self.stockpile.refresh_from_db()
        self.assertEqual(self.stockpile.stored, 0)

    def test_zero_food_ratio_zero(self):
        """No stockpile row -> ratio 0.0."""
        self.stockpile.delete()

        ratio = provision_ship_leg(self.voyage)
        self.voyage.refresh_from_db()

        self.assertEqual(ratio, 0.0)
        self.assertEqual(self.voyage.provisioning_ratio, 0.0)

    def test_no_owner_persona_ratio_zero(self):
        """Ship with no owner_persona -> ratio 0.0."""
        self.ship.building.owner_persona = None
        self.ship.building.save()

        ratio = provision_ship_leg(self.voyage)
        self.voyage.refresh_from_db()

        self.assertEqual(ratio, 0.0)

    def test_zero_crew_capacity_ratio_one(self):
        """crew_capacity == 0 -> ratio 1.0 (no crew to feed)."""
        self.ship.crew_capacity = 0
        self.ship.save()

        ratio = provision_ship_leg(self.voyage)
        self.voyage.refresh_from_db()

        self.assertEqual(ratio, 1.0)

    def test_multiple_orgs_proportional(self):
        """Persona leading multiple orgs -> food drawn from all orgs' domains."""
        from world.areas.factories import AreaFactory
        from world.societies.factories import (
            OrganizationFactory,
            OrganizationMembershipFactory,
        )
        from world.societies.houses.models import Domain

        org2 = OrganizationFactory()
        OrganizationMembershipFactory(
            organization=org2,
            persona=self.persona,
            rank=1,
        )
        domain2 = Domain.objects.create(
            area=AreaFactory(),
            name="Domain2",
            owner_org=org2,
            population=100,
        )
        stockpile2 = FoodStockpile.objects.create(domain=domain2, stored=100)

        # needed = 10 x 5 = 50; total available = 500 + 100 = 600
        ratio = provision_ship_leg(self.voyage)
        self.voyage.refresh_from_db()

        self.assertEqual(ratio, 1.0)
        self.stockpile.refresh_from_db()
        stockpile2.refresh_from_db()
        # Both stockpiles drawn from proportionally
        total_deducted = (500 - self.stockpile.stored) + (100 - stockpile2.stored)
        self.assertEqual(total_deducted, 50)

    def test_persona_not_leader_ratio_zero(self):
        """Persona with no leadership rank in any org -> ratio 0.0."""
        from world.character_sheets.factories import CharacterSheetFactory
        from world.ships.factories import ShipDetailsFactory

        # Create a ship owned by a persona with NO org memberships
        stranger_sheet = CharacterSheetFactory()
        stranger_persona = stranger_sheet.primary_persona
        stranger_ship = ShipDetailsFactory(building__owner_persona=stranger_persona)

        # Swap voyage to the stranger's ship
        self.voyage.ship = stranger_ship
        self.voyage.save()

        ratio = provision_ship_leg(self.voyage)
        self.voyage.refresh_from_db()

        self.assertEqual(ratio, 0.0)
