"""Tests for ship construction service + SHIP_CONSTRUCTION handler (#1832 Task 3)."""

from __future__ import annotations

from django.test import TestCase, tag

from world.covenants.factories import CovenantFactory
from world.locations.services import effective_owner, is_owner
from world.projects.constants import ProjectKind
from world.projects.services import get_kind_handler
from world.scenes.factories import PersonaFactory
from world.ships.constants import SHIP_KIND_NAME
from world.ships.factories import ShipTypeFactory
from world.ships.models import ShipConstructionDetails, ShipDetails
from world.ships.seeds import ensure_ship_kind
from world.ships.services import complete_ship_construction, start_ship_construction
from world.societies.factories import OrganizationMembershipFactory


class EnsureShipKindTests(TestCase):
    def test_seeds_maritime_kind(self) -> None:
        kind = ensure_ship_kind()

        self.assertEqual(kind.name, SHIP_KIND_NAME)
        self.assertTrue(kind.is_maritime)

    def test_idempotent(self) -> None:
        first = ensure_ship_kind()
        second = ensure_ship_kind()

        self.assertEqual(first.pk, second.pk)


class StartShipConstructionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.persona = PersonaFactory()
        cls.ship_type = ShipTypeFactory(base_hull=15, base_crew_capacity=20, base_cargo_capacity=30)

    def test_creates_project_and_construction_details(self) -> None:
        project = start_ship_construction(
            persona=self.persona, ship_type=self.ship_type, name="The Wavecutter"
        )

        self.assertEqual(project.kind, ProjectKind.SHIP_CONSTRUCTION)
        self.assertEqual(project.owner_persona, self.persona)

        details = ShipConstructionDetails.objects.get(project=project)
        self.assertEqual(details.ship_type, self.ship_type)
        self.assertEqual(details.name, "The Wavecutter")
        self.assertEqual(details.owner_persona, self.persona)
        self.assertIsNone(details.owner_covenant)
        self.assertIsNone(details.applied_at)
        self.assertIsNone(details.resulting_ship)

    def test_covenant_owner_is_recorded_on_details(self) -> None:
        covenant = CovenantFactory()

        project = start_ship_construction(
            persona=self.persona,
            ship_type=self.ship_type,
            name="The Sovereign's Due",
            covenant=covenant,
        )

        details = ShipConstructionDetails.objects.get(project=project)
        self.assertEqual(details.owner_covenant, covenant)


class CompleteShipConstructionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.persona = PersonaFactory()
        cls.ship_type = ShipTypeFactory(base_hull=15, base_crew_capacity=20, base_cargo_capacity=30)

    def test_handler_registered_at_app_ready(self) -> None:
        handler = get_kind_handler(ProjectKind.SHIP_CONSTRUCTION)

        self.assertIs(handler, complete_ship_construction)

    def test_completes_construction_and_seeds_ship(self) -> None:
        project = start_ship_construction(
            persona=self.persona, ship_type=self.ship_type, name="The Wavecutter"
        )

        ship = complete_ship_construction(project)

        self.assertIsInstance(ship, ShipDetails)
        self.assertEqual(ship.ship_type, self.ship_type)
        self.assertEqual(ship.building.owner_persona, self.persona)
        self.assertEqual(ship.building.fortification_level, self.ship_type.base_hull)
        self.assertEqual(ship.building.kind.name, SHIP_KIND_NAME)
        self.assertIsNotNone(ship.building.entry_room)
        self.assertEqual(ship.crew_capacity, self.ship_type.base_crew_capacity)
        self.assertEqual(ship.cargo_capacity, self.ship_type.base_cargo_capacity)

        details = ShipConstructionDetails.objects.get(project=project)
        self.assertIsNotNone(details.applied_at)
        self.assertEqual(details.resulting_ship, ship)

    def test_completion_is_idempotent(self) -> None:
        project = start_ship_construction(
            persona=self.persona, ship_type=self.ship_type, name="The Wavecutter"
        )

        first = complete_ship_construction(project)
        second = complete_ship_construction(project)

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(ShipDetails.objects.count(), 1)

    @tag("postgres")
    def test_covenant_owner_gets_location_ownership(self) -> None:
        """PG-only: ``is_owner``/``effective_owner`` walk ``AreaClosure``, a materialized
        view that doesn't exist on the SQLite inner-loop tier — see world.areas.models."""
        covenant = CovenantFactory()
        member = PersonaFactory()
        OrganizationMembershipFactory(organization=covenant.organization, persona=member)

        project = start_ship_construction(
            persona=self.persona,
            ship_type=self.ship_type,
            name="The Sovereign's Due",
            covenant=covenant,
        )

        ship = complete_ship_construction(project)
        entry_objectdb = ship.building.entry_room.objectdb

        self.assertTrue(is_owner(member, entry_objectdb))
        ownership = effective_owner(entry_objectdb)
        self.assertIsNotNone(ownership)
        self.assertEqual(ownership.holder_organization, covenant.organization)
