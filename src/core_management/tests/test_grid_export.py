"""Tests for the grid bundle exporter (#2436/#2448)."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile

from django.test import TestCase
from evennia.utils import create as evennia_create

from core_management.content_export import ContentExportError
from core_management.grid_export import export_grid_bundles
from core_management.tests._grid_fixtures import build_sample_grid
from evennia_extensions.constants import ExitKind, RoomEnclosure
from world.areas.constants import AreaLevel, GridOrigin
from world.areas.models import Area
from world.buildings.constants import PermitEligibility
from world.locations.constants import LocationParentType, StatKey


class GridExportTests(TestCase):
    """End-to-end: export the grid to a temp dir, verify bundle format."""

    @classmethod
    def setUpTestData(cls) -> None:
        grid = build_sample_grid()
        cls.realm = grid.realm
        cls.climate = grid.climate
        cls.society = grid.society
        cls.building_kind = grid.building_kind
        cls.size_tier = grid.size_tier
        cls.region = grid.region
        cls.city = grid.city
        cls.taproom_obj = grid.taproom_obj
        cls.taproom = grid.taproom
        cls.market_obj = grid.market_obj
        cls.market = grid.market
        cls.player_room_obj = grid.player_room_obj
        cls.player_room = grid.player_room
        cls.north_exit = grid.north_exit
        cls.south_exit = grid.south_exit
        cls.stray_exit = grid.stray_exit
        cls.torn_letter = grid.torn_letter
        cls.room_clue = grid.room_clue
        cls.clue_trigger = grid.clue_trigger
        cls.mirror_kind = grid.mirror_kind
        cls.portal_anchor = grid.portal_anchor

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
        self.assertEqual(authored_modifier["change_per_day"], 0)

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

    def test_authored_room_with_no_area_raises(self) -> None:
        """An AUTHORED room whose ``area`` is NULL is silently unexportable (#2448)."""
        homeless_obj = evennia_create.create_object(
            typeclass="typeclasses.rooms.Room", key="Homeless Room", nohome=True
        )
        homeless_room = homeless_obj.room_profile
        homeless_room.origin = GridOrigin.AUTHORED
        homeless_room.fixture_key = "arx-city/homeless-room"
        # area deliberately left unset (NULL).
        homeless_room.save()

        with self.assertRaisesRegex(ContentExportError, "arx-city/homeless-room"):
            export_grid_bundles(self.root)

    def test_bundle_includes_clues_triggers_and_portal_anchors(self) -> None:
        export_grid_bundles(self.root)
        bundle = self._load_bundle("arx-city")

        self.assertEqual(
            bundle["clues"],
            [
                {
                    "fixture_key": "arx-city/golden-hart-taproom/torn-letter",
                    "room": "arx-city/golden-hart-taproom",
                    "clue": "torn-letter",
                    "detect_difficulty": 5,
                    "eligibility_rule": {},
                    "is_active": True,
                }
            ],
        )
        self.assertEqual(
            bundle["clue_triggers"],
            [
                {
                    "fixture_key": "arx-city/golden-hart-taproom/whisper",
                    "room": "arx-city/golden-hart-taproom",
                    "clue": "torn-letter",
                    "eligibility_rule": {},
                    "is_active": True,
                }
            ],
        )
        self.assertEqual(
            bundle["portal_anchors"],
            [
                {
                    "fixture_key": "arx-city/golden-hart-taproom/mirror",
                    "room": "arx-city/golden-hart-taproom",
                    "kind": "Mirror",
                    "name": "a tall silvered mirror",
                    "is_network_open": True,
                }
            ],
        )

    def test_bundle_includes_ambient_lines_with_nested_conditions(self) -> None:
        from world.narrative.constants import ConditionType
        from world.narrative.factories import AmbientEmoteConditionFactory, AmbientEmoteLineFactory
        from world.species.factories import SpeciesFactory

        species = SpeciesFactory(name="Infernal")
        line = AmbientEmoteLineFactory(
            parent_type=LocationParentType.ROOM,
            room_profile=self.taproom,
            area=None,
            bystander_body="A murmur runs through the taproom.",
        )
        AmbientEmoteConditionFactory(
            line=line, condition_type=ConditionType.SPECIES, species=species
        )

        result = export_grid_bundles(self.root)
        self.assertEqual(result.errors, [])
        bundle = self._load_bundle("arx-city")

        self.assertEqual(len(bundle["ambient_lines"]), 1)
        entry = bundle["ambient_lines"][0]
        self.assertEqual(entry["parent_type"], LocationParentType.ROOM)
        self.assertEqual(entry["room"], self.taproom.fixture_key)
        self.assertEqual(entry["condition_connector"], line.condition_connector)
        self.assertEqual(entry["bystander_body"], "A murmur runs through the taproom.")
        self.assertEqual(entry["arriver_body"], line.arriver_body)
        self.assertEqual(entry["weight"], 1)
        self.assertEqual(entry["fire_chance"], 100)
        self.assertEqual(entry["cooldown_minutes"], 0)
        self.assertTrue(entry["is_active"])

        self.assertEqual(len(entry["conditions"]), 1)
        condition = entry["conditions"][0]
        self.assertEqual(condition["condition_type"], ConditionType.SPECIES)
        self.assertEqual(condition["species"], "Infernal")
        self.assertIsNone(condition["resonance"])
        self.assertIsNone(condition["minimum_value"])
        self.assertIsNone(condition["distinction"])
        self.assertIsNone(condition["min_fame_tier"])
        self.assertIsNone(condition["perceiving_society"])

    def test_authored_room_in_non_authored_area_raises(self) -> None:
        """An AUTHORED room housed by a non-AUTHORED (e.g. STORY) area is also
        silently unexportable (#2448) — the area itself must be AUTHORED."""
        story_area = Area.objects.create(
            name="GM Pocket Dimension",
            level=AreaLevel.CITY,
            origin=GridOrigin.STORY,
        )
        misplaced_obj = evennia_create.create_object(
            typeclass="typeclasses.rooms.Room", key="Misplaced Room", nohome=True
        )
        misplaced_room = misplaced_obj.room_profile
        misplaced_room.area = story_area
        misplaced_room.origin = GridOrigin.AUTHORED
        misplaced_room.fixture_key = "arx-city/misplaced-room"
        misplaced_room.save()

        with self.assertRaisesRegex(ContentExportError, "arx-city/misplaced-room"):
            export_grid_bundles(self.root)
