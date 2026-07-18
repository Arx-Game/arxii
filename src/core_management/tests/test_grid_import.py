"""Tests for the grid bundle importer (#2436/#2448)."""

from __future__ import annotations

from datetime import timedelta
import json
from pathlib import Path
import tempfile

from django.test import TestCase
from django.utils import timezone
from evennia.objects.models import ObjectDB
from evennia.utils import create as evennia_create

from core_management.content_fixtures import ContentError
from core_management.grid_export import export_grid_bundles
from core_management.grid_import import load_grid_bundles
from core_management.tests._grid_fixtures import build_sample_grid
from evennia_extensions.constants import ExitKind
from evennia_extensions.models import ExitProfile, ObjectDisplayData, RoomProfile
from world.areas.constants import AreaLevel, GridOrigin
from world.areas.models import Area
from world.locations.constants import LocationParentType, StatKey
from world.locations.models import LocationValueModifier, LocationValueOverride


class GridImportTests(TestCase):
    """End-to-end: export the grid, mutate the DB, reload, verify the graph."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.grid = build_sample_grid()

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _bundle_path(self, slug: str) -> Path:
        return self.root / "fixtures" / "grid" / f"{slug}.json"

    def _load_bundle(self, slug: str) -> dict:
        return json.loads(self._bundle_path(slug).read_text(encoding="utf-8"))

    def _write_bundle(self, slug: str, data: dict) -> None:
        self._bundle_path(slug).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def test_fresh_load_creates_graph(self) -> None:
        export_grid_bundles(self.root)

        # Wipe every AUTHORED row the export captured — rooms/exits cascade-drop
        # their display data, profiles, and sidecar rows; areas drop last (city
        # before region, since Area.parent is PROTECT).
        ObjectDB.objects.filter(
            pk__in=[
                self.grid.north_exit.pk,
                self.grid.south_exit.pk,
                self.grid.stray_exit.pk,
                self.grid.taproom_obj.pk,
                self.grid.market_obj.pk,
                self.grid.player_room_obj.pk,
            ]
        ).delete()
        self.grid.city.delete()
        self.grid.region.delete()

        result = load_grid_bundles(self.root)

        self.assertEqual(result.created_areas, 2)
        self.assertEqual(result.created_rooms, 2)
        self.assertEqual(result.created_exits, 2)
        self.assertEqual(result.errors, [])

        region = Area.objects.get(slug="arx-region")
        self.assertIsNone(region.parent)
        city = Area.objects.get(slug="arx-city")
        self.assertEqual(city.parent_id, region.pk)
        self.assertEqual(city.origin, GridOrigin.AUTHORED)
        self.assertEqual(city.realm.name, "Arx")
        self.assertEqual(city.climate.name, "Temperate")
        self.assertEqual(city.dominant_society.name, "The Compact")
        self.assertEqual(
            list(city.allowed_building_kinds.values_list("name", flat=True)), ["Tavern"]
        )

        taproom = RoomProfile.objects.get(fixture_key="arx-city/golden-hart-taproom")
        self.assertEqual(taproom.area_id, city.pk)
        self.assertEqual(taproom.origin, GridOrigin.AUTHORED)
        self.assertEqual(taproom.objectdb.db_key, "Golden Hart Taproom")
        self.assertEqual(taproom.size.name, "Modest")
        display = ObjectDisplayData.objects.get(object=taproom.objectdb)
        self.assertEqual(display.longname, "The Golden Hart Taproom, Warm and Loud")
        self.assertEqual(display.permanent_description, "A cozy tavern full of laughter.")

        market = RoomProfile.objects.get(fixture_key="arx-city/market-square")
        self.assertEqual(market.area_id, city.pk)

        north = ObjectDB.objects.get(
            db_location=taproom.objectdb, db_key="north", db_typeclass_path="typeclasses.exits.Exit"
        )
        self.assertEqual(north.db_destination_id, market.objectdb_id)
        self.assertEqual(set(north.aliases.all()), {"n"})
        north_profile = ExitProfile.objects.get(objectdb=north)
        self.assertEqual(north_profile.exit_kind, ExitKind.WINDOW)
        self.assertTrue(north_profile.is_open)

        south = ObjectDB.objects.get(
            db_location=market.objectdb, db_key="south", db_typeclass_path="typeclasses.exits.Exit"
        )
        self.assertEqual(south.db_destination_id, taproom.objectdb_id)

        override = LocationValueOverride.objects.get(
            parent_type=LocationParentType.ROOM, room_profile=taproom
        )
        self.assertEqual(override.stat_key, StatKey.LIGHTING)
        self.assertEqual(override.value, 1)

        modifier = LocationValueModifier.objects.get(
            parent_type=LocationParentType.AREA, area=city, source="authored:city-watch"
        )
        self.assertEqual(modifier.stat_key, StatKey.ORDER)
        self.assertEqual(modifier.value, 3)

    def test_reimport_updates_in_place(self) -> None:
        export_grid_bundles(self.root)
        original_pk = self.grid.taproom_obj.pk

        bundle = self._load_bundle("arx-city")
        for room in bundle["rooms"]:
            if room["fixture_key"] == "arx-city/golden-hart-taproom":
                room["description"] = "Freshly rebuilt after the fire."
        self._write_bundle("arx-city", bundle)

        result = load_grid_bundles(self.root)

        self.assertEqual(result.created_rooms, 0)
        self.assertEqual(result.updated_rooms, 2)
        self.assertEqual(RoomProfile.objects.filter(fixture_key__startswith="arx-city/").count(), 2)

        taproom = RoomProfile.objects.get(fixture_key="arx-city/golden-hart-taproom")
        self.assertEqual(taproom.objectdb_id, original_pk)
        display = ObjectDisplayData.objects.get(object_id=original_pk)
        self.assertEqual(display.permanent_description, "Freshly rebuilt after the fire.")

    def test_dangling_exit_destination_raises_content_error(self) -> None:
        export_grid_bundles(self.root)

        bundle = self._load_bundle("arx-city")
        bundle["exits"].append(
            {
                "source": "arx-city/golden-hart-taproom",
                "key": "trapdoor",
                "aliases": [],
                "destination": "arx-city/nonexistent-cellar",
                "exit_kind": ExitKind.DOOR,
                "is_open": False,
            }
        )
        self._write_bundle("arx-city", bundle)

        with self.assertRaises(ContentError):
            load_grid_bundles(self.root)

    def test_db_room_absent_from_bundles_reported_not_deleted(self) -> None:
        export_grid_bundles(self.root)

        extra_obj = evennia_create.create_object(
            typeclass="typeclasses.rooms.Room", key="Forgotten Cellar", nohome=True
        )
        extra_profile = extra_obj.room_profile
        extra_profile.area = self.grid.city
        extra_profile.origin = GridOrigin.AUTHORED
        extra_profile.fixture_key = "arx-city/forgotten-cellar"
        extra_profile.save()

        result = load_grid_bundles(self.root)

        matching = [r for r in result.reports if "arx-city/forgotten-cellar" in r]
        self.assertEqual(len(matching), 1)
        self.assertTrue(
            RoomProfile.objects.filter(fixture_key="arx-city/forgotten-cellar").exists()
        )

    def test_authored_modifiers_replaced_runtime_sources_untouched(self) -> None:
        export_grid_bundles(self.root)
        weather_pk = LocationValueModifier.objects.get(source="weather:cold-snap").pk
        authored_pk = LocationValueModifier.objects.get(source="authored:city-watch").pk

        result = load_grid_bundles(self.root)

        self.assertEqual(
            LocationValueModifier.objects.filter(source="weather:cold-snap").count(), 1
        )
        self.assertEqual(
            LocationValueModifier.objects.get(source="weather:cold-snap").pk, weather_pk
        )

        authored_rows = LocationValueModifier.objects.filter(source="authored:city-watch")
        self.assertEqual(authored_rows.count(), 1)
        self.assertNotEqual(authored_rows.first().pk, authored_pk)
        self.assertEqual(authored_rows.first().value, 3)
        self.assertEqual(result.errors, [])

    def test_reimported_modifier_change_per_day_round_trips_as_int(self) -> None:
        """#2448 fix: the exporter must not stringify change_per_day, and the freshly
        created (idmapper-cached) instance must carry a real int — not a str that
        merely happens to coerce correctly on the next DB round-trip."""
        export_grid_bundles(self.root)

        bundle = self._load_bundle("arx-city")
        for modifier in bundle["modifiers"]:
            if modifier["source"] == "authored:city-watch":
                modifier["change_per_day"] = -2
        self._write_bundle("arx-city", bundle)

        result = load_grid_bundles(self.root)
        self.assertEqual(result.errors, [])

        modifier = LocationValueModifier.objects.get(
            parent_type=LocationParentType.AREA, area=self.grid.city, source="authored:city-watch"
        )
        self.assertIsInstance(modifier.change_per_day, int)
        self.assertEqual(modifier.change_per_day, -2)

        # Force the decay arithmetic path (nonzero elapsed days) rather than the
        # value==0/change_per_day==0 shortcut — this is exactly where a str
        # change_per_day raises TypeError instead of computing a decayed int.
        current = modifier.current_value(now=timezone.now() + timedelta(days=5))
        self.assertIsInstance(current, int)

    def test_db_area_absent_from_bundles_reported_not_deleted(self) -> None:
        export_grid_bundles(self.root)

        Area.objects.create(
            name="Forgotten Ward",
            level=AreaLevel.REGION,
            slug="arx-forgotten-ward",
            origin=GridOrigin.AUTHORED,
        )

        result = load_grid_bundles(self.root)

        matching = [r for r in result.reports if "arx-forgotten-ward" in r]
        self.assertEqual(len(matching), 1)
        self.assertTrue(Area.objects.filter(slug="arx-forgotten-ward").exists())

    def test_imports_clues_triggers_and_portal_anchors(self) -> None:
        from world.clues.models import ClueTrigger, RoomClue
        from world.magic.models import PortalAnchor

        export_grid_bundles(self.root)

        RoomClue.objects.all().delete()
        ClueTrigger.objects.all().delete()
        PortalAnchor.objects.all().delete()

        result = load_grid_bundles(self.root)

        self.assertEqual(result.errors, [])
        restored_clue = RoomClue.objects.get(fixture_key="arx-city/golden-hart-taproom/torn-letter")
        self.assertEqual(restored_clue.detect_difficulty, 5)
        self.assertTrue(
            ClueTrigger.objects.filter(fixture_key="arx-city/golden-hart-taproom/whisper").exists()
        )
        self.assertTrue(
            PortalAnchor.objects.active()
            .filter(fixture_key="arx-city/golden-hart-taproom/mirror")
            .exists()
        )

    def test_reimport_never_deletes_missing_sidecar(self) -> None:
        """A fixture-keyed clue/anchor absent from a reimported bundle is reported, not deleted."""
        from world.clues.factories import RoomClueFactory
        from world.clues.models import RoomClue

        export_grid_bundles(self.root)
        orphan = RoomClueFactory(
            room_profile=self.grid.taproom, fixture_key="arx-city/golden-hart-taproom/orphan"
        )

        result = load_grid_bundles(self.root)

        self.assertTrue(RoomClue.objects.filter(pk=orphan.pk).exists())
        self.assertTrue(
            any("orphan" in line for line in result.reports),
            f"expected an orphan report, got: {result.reports}",
        )
