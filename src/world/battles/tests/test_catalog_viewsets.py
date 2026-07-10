"""Journey tests for the read-only GM staging catalog API (#2010 Task 5).

Covers ``BattleMapBlueprintViewSet`` and ``BattleUnitTemplateViewSet``:
anonymous/non-GM are denied, JUNIOR-tier GM trust (or staff) can list/retrieve
both catalogs, pagination is present, and ``is_active`` filters correctly.
Permission gate mirrors ``MinimumGMLevelPrerequisite``
(src/actions/prerequisites.py) via ``world.gm.permissions.HasGMTrust``.
"""

from __future__ import annotations

from django.test import TestCase
from rest_framework import status as http_status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.battles.factories import (
    BattleMapBlueprintFactory,
    BattleUnitTemplateCapabilityFactory,
    BattleUnitTemplateFactory,
    BlueprintBattlePlaceFactory,
    BlueprintFortificationFactory,
)
from world.conditions.factories import CapabilityTypeFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory
from world.mechanics.factories import PropertyFactory


class CatalogViewSetAccessTest(TestCase):
    """Access control shared by both catalog endpoints."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.blueprint = BattleMapBlueprintFactory(name="Ford Skirmish")
        cls.template = BattleUnitTemplateFactory(name="Vanguard Pikes Template")

        cls.junior_account = AccountFactory(username="catalog_junior")
        GMProfileFactory(account=cls.junior_account, level=GMLevel.JUNIOR)

        cls.starting_account = AccountFactory(username="catalog_starting")
        GMProfileFactory(account=cls.starting_account, level=GMLevel.STARTING)

        cls.staff_account = AccountFactory(username="catalog_staff", is_staff=True)
        cls.non_gm_account = AccountFactory(username="catalog_non_gm")

    def test_anonymous_is_denied_blueprints(self) -> None:
        client = APIClient()
        response = client.get("/api/battles/map-blueprints/")
        self.assertIn(
            response.status_code,
            (http_status.HTTP_401_UNAUTHORIZED, http_status.HTTP_403_FORBIDDEN),
        )

    def test_anonymous_is_denied_unit_templates(self) -> None:
        client = APIClient()
        response = client.get("/api/battles/unit-templates/")
        self.assertIn(
            response.status_code,
            (http_status.HTTP_401_UNAUTHORIZED, http_status.HTTP_403_FORBIDDEN),
        )

    def test_authenticated_non_gm_is_forbidden_blueprints(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.non_gm_account)
        response = client.get("/api/battles/map-blueprints/")
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_authenticated_non_gm_is_forbidden_unit_templates(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.non_gm_account)
        response = client.get("/api/battles/unit-templates/")
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_starting_gm_below_junior_floor_is_forbidden(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.starting_account)
        response = client.get("/api/battles/map-blueprints/")
        self.assertEqual(response.status_code, http_status.HTTP_403_FORBIDDEN)

    def test_junior_gm_can_list_blueprints(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.junior_account)
        response = client.get("/api/battles/map-blueprints/")
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        names = [row["name"] for row in response.data["results"]]
        self.assertIn("Ford Skirmish", names)

    def test_junior_gm_can_list_unit_templates(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.junior_account)
        response = client.get("/api/battles/unit-templates/")
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        names = [row["name"] for row in response.data["results"]]
        self.assertIn("Vanguard Pikes Template", names)

    def test_staff_bypasses_gm_trust_requirement(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.staff_account)
        response = client.get("/api/battles/map-blueprints/")
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        response = client.get("/api/battles/unit-templates/")
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

    def test_blueprint_list_is_paginated(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.junior_account)
        response = client.get("/api/battles/map-blueprints/")
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        for key in ("count", "next", "previous", "results"):
            self.assertIn(key, response.data)

    def test_unit_template_list_is_paginated(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.junior_account)
        response = client.get("/api/battles/unit-templates/")
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        for key in ("count", "next", "previous", "results"):
            self.assertIn(key, response.data)

    def test_blueprint_is_active_filter(self) -> None:
        BattleMapBlueprintFactory(name="Retired Layout", is_active=False)
        client = APIClient()
        client.force_authenticate(user=self.junior_account)
        response = client.get("/api/battles/map-blueprints/?is_active=false")
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        names = [row["name"] for row in response.data["results"]]
        self.assertIn("Retired Layout", names)
        self.assertNotIn("Ford Skirmish", names)

    def test_unit_template_is_active_filter(self) -> None:
        BattleUnitTemplateFactory(name="Retired Template", is_active=False)
        client = APIClient()
        client.force_authenticate(user=self.junior_account)
        response = client.get("/api/battles/unit-templates/?is_active=false")
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        names = [row["name"] for row in response.data["results"]]
        self.assertIn("Retired Template", names)
        self.assertNotIn("Vanguard Pikes Template", names)


class BattleMapBlueprintShapeTest(TestCase):
    """Nested places + fortifications shape."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.blueprint = BattleMapBlueprintFactory(name="River Crossing", description="A ford.")
        cls.place = BlueprintBattlePlaceFactory(
            blueprint=cls.blueprint,
            name="The Ford",
            movement_cost=2,
        )
        cls.fortification = BlueprintFortificationFactory(
            blueprint_place=cls.place,
            max_integrity=150,
        )
        cls.gm_account = AccountFactory(username="blueprint_shape_gm")
        GMProfileFactory(account=cls.gm_account, level=GMLevel.JUNIOR)

    def test_retrieve_nests_places_and_fortifications(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.gm_account)
        response = client.get(f"/api/battles/map-blueprints/{self.blueprint.pk}/")
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        data = response.data
        self.assertEqual(data["name"], "River Crossing")
        self.assertEqual(len(data["places"]), 1)
        place_data = data["places"][0]
        self.assertEqual(place_data["id"], self.place.pk)
        self.assertEqual(place_data["name"], "The Ford")
        self.assertEqual(place_data["movement_cost"], 2)
        self.assertIsInstance(place_data["x"], float)
        self.assertEqual(len(place_data["fortifications"]), 1)
        fort_data = place_data["fortifications"][0]
        self.assertEqual(fort_data["id"], self.fortification.pk)
        self.assertEqual(fort_data["max_integrity"], 150)


class BattleUnitTemplateShapeTest(TestCase):
    """Nested properties (names) + capability values (names) shape."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = BattleUnitTemplateFactory(name="Storm Wardens", strength=120)
        cls.prop = PropertyFactory(name="Armored")
        cls.template.properties.add(cls.prop)
        cls.capability = CapabilityTypeFactory(name="melee_attack")
        cls.capability_value = BattleUnitTemplateCapabilityFactory(
            template=cls.template,
            capability=cls.capability,
            value=5,
        )
        cls.gm_account = AccountFactory(username="template_shape_gm")
        GMProfileFactory(account=cls.gm_account, level=GMLevel.JUNIOR)

    def test_retrieve_nests_properties_and_capability_values_by_name(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.gm_account)
        response = client.get(f"/api/battles/unit-templates/{self.template.pk}/")
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        data = response.data
        self.assertEqual(data["name"], "Storm Wardens")
        self.assertEqual(data["strength"], 120)
        self.assertEqual(len(data["properties"]), 1)
        self.assertEqual(data["properties"][0]["name"], "Armored")
        self.assertEqual(len(data["capability_values"]), 1)
        cap_data = data["capability_values"][0]
        self.assertEqual(cap_data["capability_name"], "melee_attack")
        self.assertEqual(cap_data["value"], 5)
