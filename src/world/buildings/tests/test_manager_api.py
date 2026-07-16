"""Building-manager read API (#670 PR2).

Owner-gated manager payload (rooms + exits + budget + tenancies), the
for-room resolver the RoomPanel button uses, and the two public catalogs
(room size tiers, decoration templates).
"""

from django.test import tag
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, ObjectDBFactory
from evennia_extensions.models import RoomProfile, RoomSizeTier
from evennia_extensions.seeds import ensure_room_size_tiers
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.buildings.factories import BuildingFactory
from world.buildings.models import (
    PolishCategory,
    ProjectTemplate,
    ProjectTemplatePolishIncrement,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.locations.constants import HolderType, LocationParentType
from world.locations.models import LocationOwnership
from world.locations.services import assign_room_tenant, set_primary_home
from world.projects.constants import ProjectKind
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)


def _room_in(area, *, size=None, grid=(None, None, 0), name="A Room"):
    room = ObjectDBFactory(db_key=name, db_typeclass_path="typeclasses.rooms.Room")
    RoomProfile.objects.update_or_create(
        objectdb=room,
        defaults={
            "area": area,
            "size": size,
            "grid_x": grid[0],
            "grid_y": grid[1],
            "floor": grid[2],
        },
    )
    return room


def _player(account):
    """A playable character wired to ``account`` via an active roster tenure."""
    sheet = CharacterSheetFactory()
    entry = RosterEntryFactory(character_sheet=sheet)
    RosterTenureFactory(roster_entry=entry, player_data=PlayerDataFactory(account=account))
    return sheet


@tag("postgres")  # ownership/tenancy cascades walk the areas_areaclosure materialized view
class ManagerApiBase(APITestCase):
    # Fixtures live in setUp, NOT setUpTestData: Django deep-copies
    # setUpTestData attributes per test, and Evennia typeclass objects (or
    # models whose fields_cache reaches one) carry an un-deepcopyable
    # DbHolder once their attribute handler attaches — an ordering-sensitive
    # CI failure. Instance attributes are never deep-copied.
    def setUp(self) -> None:
        ensure_room_size_tiers()
        self.modest = RoomSizeTier.objects.get(name="Modest")
        self.snug = RoomSizeTier.objects.get(name="Snug")

        self.owner_account = AccountFactory()
        self.owner_sheet = _player(self.owner_account)
        self.owner_persona = self.owner_sheet.primary_persona

        area = AreaFactory(level=AreaLevel.BUILDING, name="Gilded Hall")
        self.building = BuildingFactory(area=area, space_budget=100)
        LocationOwnership.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            holder_type=HolderType.PERSONA,
            holder_persona=self.owner_persona,
        )
        self.entry = _room_in(area, size=self.modest, grid=(0, 0, 0), name="Entry Hall")
        self.building.entry_room = self.entry.room_profile
        self.building.save(update_fields=["entry_room"])
        self.study = _room_in(area, size=self.snug, grid=(1, 0, 0), name="Study")
        self.attic = _room_in(area, size=self.snug, grid=(0, 0, 1), name="Attic")

        # One exit pair entry <-> study.
        self.exit_out = ObjectDBFactory(
            db_key="east",
            db_typeclass_path="typeclasses.exits.Exit",
            location=self.entry,
            destination=self.study,
        )
        self.exit_back = ObjectDBFactory(
            db_key="west",
            db_typeclass_path="typeclasses.exits.Exit",
            location=self.study,
            destination=self.entry,
        )

        # A tenant with a primary home in the study.
        self.tenant_account = AccountFactory()
        self.tenant_sheet = _player(self.tenant_account)
        self.tenant_persona = self.tenant_sheet.primary_persona
        assign_room_tenant(
            persona=self.owner_persona, room=self.study, tenant_persona=self.tenant_persona
        )
        set_primary_home(persona=self.tenant_persona, room=self.study)

    def _get(self, url, account, **params):
        self.client.force_authenticate(user=account)
        return self.client.get(url, params)


class ManagerDetailTests(ManagerApiBase):
    def _url(self) -> str:
        return f"/api/buildings/manager/{self.building.pk}/"

    def test_requires_authentication(self) -> None:
        response = self.client.get(self._url(), {"character_id": self.owner_sheet.pk})
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_missing_character_id_is_400(self) -> None:
        self.client.force_authenticate(user=self.owner_account)
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unowned_character_is_404(self) -> None:
        response = self._get(self._url(), self.owner_account, character_id=self.tenant_sheet.pk)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_non_owner_is_403(self) -> None:
        response = self._get(self._url(), self.tenant_account, character_id=self.tenant_sheet.pk)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_gets_full_payload(self) -> None:
        response = self._get(self._url(), self.owner_account, character_id=self.owner_sheet.pk)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        building = data["building"]
        self.assertEqual(building["id"], self.building.pk)
        self.assertEqual(building["name"], "Gilded Hall")
        self.assertEqual(building["space_budget"], 100)
        self.assertEqual(building["space_used"], 45)  # Modest 25 + Snug 10 + Snug 10
        self.assertEqual(building["space_remaining"], 55)
        self.assertEqual(building["entry_room_id"], self.entry.pk)
        self.assertEqual(building["floors"], [0, 1])

        rooms = {r["name"]: r for r in data["rooms"]}
        self.assertEqual(set(rooms), {"Entry Hall", "Study", "Attic"})
        self.assertTrue(rooms["Entry Hall"]["is_entry"])
        self.assertFalse(rooms["Study"]["is_entry"])
        self.assertEqual(rooms["Study"]["size_name"], "Snug")
        self.assertEqual(rooms["Study"]["size_units"], 10)
        self.assertEqual(
            (rooms["Study"]["grid_x"], rooms["Study"]["grid_y"], rooms["Study"]["floor"]),
            (1, 0, 0),
        )

        tenancies = rooms["Study"]["tenancies"]
        self.assertEqual(len(tenancies), 1)
        self.assertEqual(tenancies[0]["tenant_persona_id"], self.tenant_persona.pk)
        self.assertTrue(tenancies[0]["is_primary_home"])
        self.assertEqual(rooms["Entry Hall"]["tenancies"], [])

        exits = {(e["from_room_id"], e["to_room_id"]): e for e in data["exits"]}
        self.assertIn((self.entry.pk, self.study.pk), exits)
        self.assertIn((self.study.pk, self.entry.pk), exits)
        self.assertEqual(exits[(self.entry.pk, self.study.pk)]["name"], "east")

    def test_detail_query_budget(self) -> None:
        self.client.force_authenticate(user=self.owner_account)
        url = self._url()
        # Warm-up request so SharedMemoryModel identity-map effects settle.
        self.client.get(url, {"character_id": self.owner_sheet.pk})
        with self.assertNumQueries(12):
            response = self.client.get(url, {"character_id": self.owner_sheet.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class ForRoomResolverTests(ManagerApiBase):
    def _url(self, room) -> str:
        return f"/api/buildings/manager/for-room/{room.pk}/"

    def test_owner_flags(self) -> None:
        response = self._get(
            self._url(self.entry), self.owner_account, character_id=self.owner_sheet.pk
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["building_id"], self.building.pk)
        self.assertTrue(data["is_owner"])
        self.assertFalse(data["is_tenant"])
        self.assertFalse(data["is_primary_home_here"])

    def test_tenant_flags(self) -> None:
        response = self._get(
            self._url(self.study), self.tenant_account, character_id=self.tenant_sheet.pk
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertFalse(data["is_owner"])
        self.assertTrue(data["is_tenant"])
        self.assertTrue(data["is_primary_home_here"])

    def test_room_outside_any_building(self) -> None:
        ward = AreaFactory(level=AreaLevel.WARD)
        street = _room_in(ward, name="Open Street")
        response = self._get(
            self._url(street), self.owner_account, character_id=self.owner_sheet.pk
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.json()["building_id"])


class CatalogTests(ManagerApiBase):
    def test_size_tiers_listed_by_units(self) -> None:
        response = self._get("/api/buildings/room-size-tiers/", self.owner_account)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.json()["results"]
        units = [row["units"] for row in results]
        self.assertEqual(units, sorted(units))
        self.assertIn("Modest", {row["name"] for row in results})

    def test_decoration_templates_scoped_to_interior_design(self) -> None:
        category = PolishCategory.objects.create(name="Elegance")
        template = ProjectTemplate.objects.create(
            name="Silk Drapery",
            description="PLACEHOLDER — fine hangings.",
            base_cost=500,
            project_kind=ProjectKind.INTERIOR_DESIGN,
        )
        ProjectTemplatePolishIncrement.objects.create(
            template=template, category=category, value=40
        )
        ProjectTemplate.objects.create(
            name="Not A Decoration",
            base_cost=1,
            project_kind=ProjectKind.BUILDING_CONSTRUCTION,
        )

        response = self._get("/api/buildings/decoration-templates/", self.owner_account)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = {row["name"] for row in response.json()["results"]}
        self.assertIn("Silk Drapery", names)
        self.assertNotIn("Not A Decoration", names)

        drapery = next(row for row in response.json()["results"] if row["name"] == "Silk Drapery")
        self.assertEqual(drapery["base_cost"], 500)
        self.assertEqual(drapery["increments"], [{"category": "Elegance", "value": 40}])

    def test_decoration_template_search(self) -> None:
        ProjectTemplate.objects.create(
            name="Marble Floor", base_cost=900, project_kind=ProjectKind.INTERIOR_DESIGN
        )
        ProjectTemplate.objects.create(
            name="Silk Cushions", base_cost=100, project_kind=ProjectKind.INTERIOR_DESIGN
        )
        response = self._get(
            "/api/buildings/decoration-templates/", self.owner_account, search="Marble"
        )
        names = {row["name"] for row in response.json()["results"]}
        self.assertEqual(names, {"Marble Floor"})
