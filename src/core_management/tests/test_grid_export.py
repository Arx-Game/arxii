"""Tests for the grid bundle exporter (#2436/#2448)."""

from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path
import tempfile

from django.test import TestCase
from evennia.utils import create as evennia_create

from core_management.content_export import ContentExportError
from core_management.grid_export import export_grid_bundles
from evennia_extensions.constants import ExitKind, RoomEnclosure
from evennia_extensions.models import ExitProfile, ObjectDisplayData, RoomSizeTier
from world.areas.constants import AreaLevel, GridOrigin
from world.areas.models import Area
from world.buildings.constants import PermitEligibility
from world.buildings.models import BuildingKind
from world.locations.constants import LocationParentType, StatKey
from world.locations.models import LocationValueModifier, LocationValueOverride
from world.realms.models import Realm
from world.societies.models import Society
from world.weather.models import Climate


class GridExportTests(TestCase):
    """End-to-end: export the grid to a temp dir, verify bundle format."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.realm = Realm.objects.create(name="Arx")
        cls.climate = Climate.objects.create(name="Temperate")
        cls.society = Society.objects.create(name="The Compact", realm=cls.realm)
        cls.building_kind = BuildingKind.objects.create(name="Tavern")
        cls.size_tier = RoomSizeTier.objects.create(name="Modest", units=10)

        cls.region = Area.objects.create(
            name="Arx Region",
            level=AreaLevel.REGION,
            slug="arx-region",
            origin=GridOrigin.AUTHORED,
        )
        cls.city = Area.objects.create(
            name="Arx City",
            level=AreaLevel.CITY,
            parent=cls.region,
            slug="arx-city",
            origin=GridOrigin.AUTHORED,
            realm=cls.realm,
            climate=cls.climate,
            dominant_society=cls.society,
            description="The City of Arx.",
            color="|y",
            permit_eligibility=PermitEligibility.OPEN,
            permit_cost_multiplier=Decimal("1.500"),
        )
        cls.city.allowed_building_kinds.add(cls.building_kind)

        cls.taproom_obj = evennia_create.create_object(
            typeclass="typeclasses.rooms.Room", key="Golden Hart Taproom", nohome=True
        )
        cls.taproom = cls.taproom_obj.room_profile
        cls.taproom.area = cls.city
        cls.taproom.origin = GridOrigin.AUTHORED
        cls.taproom.fixture_key = "arx-city/golden-hart-taproom"
        cls.taproom.is_public = True
        cls.taproom.is_social_hub = True
        cls.taproom.is_outdoor = False
        cls.taproom.enclosure = RoomEnclosure.WALLED
        cls.taproom.size = cls.size_tier
        cls.taproom.grid_x = 0
        cls.taproom.grid_y = 0
        cls.taproom.floor = 0
        cls.taproom.save()
        ObjectDisplayData.objects.create(
            object=cls.taproom_obj,
            longname="The Golden Hart Taproom, Warm and Loud",
            permanent_description="A cozy tavern full of laughter.",
        )

        cls.market_obj = evennia_create.create_object(
            typeclass="typeclasses.rooms.Room", key="Market Square", nohome=True
        )
        cls.market = cls.market_obj.room_profile
        cls.market.area = cls.city
        cls.market.origin = GridOrigin.AUTHORED
        cls.market.fixture_key = "arx-city/market-square"
        cls.market.is_public = True
        cls.market.enclosure = RoomEnclosure.OPEN_AIR
        cls.market.grid_x = 1
        cls.market.grid_y = 0
        cls.market.save()

        # PLAYER-origin room in the same area — never exported.
        cls.player_room_obj = evennia_create.create_object(
            typeclass="typeclasses.rooms.Room", key="Someone's Den", nohome=True
        )
        cls.player_room = cls.player_room_obj.room_profile
        cls.player_room.area = cls.city
        cls.player_room.save()

        cls.north_exit = evennia_create.create_object(
            typeclass="typeclasses.exits.Exit",
            key="north",
            location=cls.taproom_obj,
            destination=cls.market_obj,
            aliases=["n"],
            nohome=True,
        )
        ExitProfile.objects.create(objectdb=cls.north_exit, exit_kind=ExitKind.WINDOW, is_open=True)

        cls.south_exit = evennia_create.create_object(
            typeclass="typeclasses.exits.Exit",
            key="south",
            location=cls.market_obj,
            destination=cls.taproom_obj,
            aliases=["s"],
            nohome=True,
        )
        # No ExitProfile row — exercises the DOOR/closed default fallback.

        # Exit to an unauthored (PLAYER-origin) destination — must be skipped + reported.
        cls.stray_exit = evennia_create.create_object(
            typeclass="typeclasses.exits.Exit",
            key="hole in the wall",
            location=cls.taproom_obj,
            destination=cls.player_room_obj,
            nohome=True,
        )

        LocationValueOverride.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=cls.taproom,
            stat_key=StatKey.LIGHTING,
            value=1,
        )
        LocationValueModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=cls.city,
            stat_key=StatKey.ORDER,
            value=3,
            change_per_day=0,
            source="authored:city-watch",
        )
        LocationValueModifier.objects.create(
            parent_type=LocationParentType.AREA,
            area=cls.city,
            stat_key=StatKey.COLD,
            value=20,
            change_per_day=-1,
            source="weather:cold-snap",
        )

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _load_bundle(self, slug: str) -> dict:
        path = self.root / "fixtures" / "grid" / f"{slug}.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_writes_one_bundle_per_authored_area(self) -> None:
        result = export_grid_bundles(self.root)

        self.assertEqual(result.area_count, 2)
        written_names = {p.name for p in result.written}
        self.assertEqual(written_names, {"arx-region.json", "arx-city.json"})

        region_bundle = self._load_bundle("arx-region")
        self.assertEqual(region_bundle["format"], 1)
        self.assertEqual(region_bundle["area"]["slug"], "arx-region")
        self.assertIsNone(region_bundle["area"]["parent"])

        city_bundle = self._load_bundle("arx-city")
        self.assertEqual(city_bundle["format"], 1)
        self.assertEqual(city_bundle["area"]["slug"], "arx-city")
        self.assertEqual(city_bundle["area"]["parent"], "arx-region")
        self.assertEqual(city_bundle["area"]["realm"], "Arx")
        self.assertEqual(city_bundle["area"]["climate"], "Temperate")
        self.assertEqual(city_bundle["area"]["dominant_society"], "The Compact")
        self.assertEqual(city_bundle["area"]["level"], AreaLevel.CITY)
        self.assertEqual(city_bundle["area"]["permit_eligibility"], PermitEligibility.OPEN)
        self.assertEqual(city_bundle["area"]["permit_cost_multiplier"], "1.500")
        self.assertEqual(city_bundle["area"]["allowed_building_kinds"], ["Tavern"])

    def test_rooms_and_exits_captured_with_display_data(self) -> None:
        export_grid_bundles(self.root)
        bundle = self._load_bundle("arx-city")

        rooms_by_key = {r["fixture_key"]: r for r in bundle["rooms"]}
        self.assertEqual(
            set(rooms_by_key), {"arx-city/golden-hart-taproom", "arx-city/market-square"}
        )
        taproom_data = rooms_by_key["arx-city/golden-hart-taproom"]
        self.assertEqual(taproom_data["key"], "Golden Hart Taproom")
        self.assertEqual(taproom_data["longname"], "The Golden Hart Taproom, Warm and Loud")
        self.assertEqual(taproom_data["description"], "A cozy tavern full of laughter.")
        self.assertTrue(taproom_data["is_public"])
        self.assertTrue(taproom_data["is_social_hub"])
        self.assertFalse(taproom_data["is_outdoor"])
        self.assertEqual(taproom_data["enclosure"], RoomEnclosure.WALLED)
        self.assertEqual(taproom_data["size"], "Modest")
        self.assertEqual(taproom_data["grid_x"], 0)
        self.assertEqual(taproom_data["grid_y"], 0)
        self.assertEqual(taproom_data["floor"], 0)

        # Market Square never got an ObjectDisplayData row — fields fall back to "".
        market_data = rooms_by_key["arx-city/market-square"]
        self.assertEqual(market_data["longname"], "")
        self.assertEqual(market_data["description"], "")
        self.assertIsNone(market_data["size"])

        exits_by_key = {(e["source"], e["key"]): e for e in bundle["exits"]}
        north = exits_by_key[("arx-city/golden-hart-taproom", "north")]
        self.assertEqual(north["aliases"], ["n"])
        self.assertEqual(north["destination"], "arx-city/market-square")
        self.assertEqual(north["exit_kind"], ExitKind.WINDOW)
        self.assertTrue(north["is_open"])

        south = exits_by_key[("arx-city/market-square", "south")]
        self.assertEqual(south["aliases"], ["s"])
        self.assertEqual(south["destination"], "arx-city/golden-hart-taproom")
        # No ExitProfile row was created for this exit — defaults apply.
        self.assertEqual(south["exit_kind"], ExitKind.DOOR)
        self.assertFalse(south["is_open"])

    def test_exit_to_unkeyed_destination_skipped_with_report(self) -> None:
        result = export_grid_bundles(self.root)
        bundle = self._load_bundle("arx-city")

        exit_keys = {(e["source"], e["key"]) for e in bundle["exits"]}
        self.assertNotIn(("arx-city/golden-hart-taproom", "hole in the wall"), exit_keys)

        matching_reports = [r for r in result.reports if "hole in the wall" in r]
        self.assertEqual(len(matching_reports), 1)
        self.assertIn("destination not authored", matching_reports[0])

    def test_runtime_modifier_sources_excluded(self) -> None:
        export_grid_bundles(self.root)
        bundle = self._load_bundle("arx-city")

        sources = {m["source"] for m in bundle["modifiers"]}
        self.assertIn("authored:city-watch", sources)
        self.assertNotIn("weather:cold-snap", sources)

        override = bundle["overrides"][0]
        self.assertEqual(override["parent_type"], LocationParentType.ROOM)
        self.assertEqual(override["room"], "arx-city/golden-hart-taproom")
        self.assertEqual(override["stat_key"], StatKey.LIGHTING)
        self.assertEqual(override["value"], 1)

        authored_modifier = next(
            m for m in bundle["modifiers"] if m["source"] == "authored:city-watch"
        )
        self.assertEqual(authored_modifier["parent_type"], LocationParentType.AREA)
        self.assertIsNone(authored_modifier["room"])
        self.assertEqual(authored_modifier["stat_key"], StatKey.ORDER)
        self.assertEqual(authored_modifier["value"], 3)
        self.assertEqual(authored_modifier["change_per_day"], "0")

    def test_player_origin_room_not_exported(self) -> None:
        export_grid_bundles(self.root)
        bundle = self._load_bundle("arx-city")

        fixture_keys = {r["fixture_key"] for r in bundle["rooms"]}
        self.assertEqual(fixture_keys, {"arx-city/golden-hart-taproom", "arx-city/market-square"})
        room_names = {r["key"] for r in bundle["rooms"]}
        self.assertNotIn("Someone's Den", room_names)

    def test_authored_room_missing_fixture_key_raises(self) -> None:
        broken_room_obj = evennia_create.create_object(
            typeclass="typeclasses.rooms.Room", key="Broken Room", nohome=True
        )
        broken_room = broken_room_obj.room_profile
        broken_room.area = self.city
        broken_room.origin = GridOrigin.AUTHORED
        # fixture_key deliberately left unset.
        broken_room.save()

        with self.assertRaises(ContentExportError):
            export_grid_bundles(self.root)
