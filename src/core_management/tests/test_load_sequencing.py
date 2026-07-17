"""Tests for the ``load_world_content`` driver (#2436/#2448).

Closes the circular dependency between authored content fixtures and the
grid: a ``StartingArea`` fixture's ``default_starting_room`` names a room by
its ``RoomProfile`` natural key (``fixture_key``), but that room only exists
once the grid bundles import — a separate file tree from the content
fixtures. ``load_world_content`` sequences content fixtures (deferring an
unresolved natural-key FK target instead of skipping it) -> grid bundles ->
one retry of every deferred object, closing the loop.
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile

from django.test import TestCase
from evennia.objects.models import ObjectDB

from core_management.content_export import export_to_content_repo
from core_management.content_fixtures import load_world_content
from core_management.grid_export import export_grid_bundles
from core_management.tests._grid_fixtures import build_sample_grid
from evennia_extensions.models import RoomProfile
from world.areas.models import Area
from world.character_creation.constants import FALLBACK_STARTING_ROOM_FIXTURE_KEY
from world.character_creation.models import StartingArea
from world.seeds.character_creation import ensure_canonical_fallback_room
from world.traits.models import Trait

GOOD_SKILL = """---
name: Performance
category: social
---
PLACEHOLDER Captivating an audience through music, oration, or storytelling.
"""


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _write_starting_area_fixture(root: Path, *, name: str, description: str, room_key: str) -> None:
    _write(
        root,
        "fixtures/character_creation/startingarea.json",
        json.dumps(
            [
                {
                    "model": "character_creation.startingarea",
                    "fields": {
                        "name": name,
                        "description": description,
                        "default_starting_room": [room_key],
                    },
                },
            ]
        ),
    )


class LoadWorldContentSequencingTests(TestCase):
    """End-to-end: content fixtures + grid bundles through ``load_world_content``."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.grid = build_sample_grid()

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_starting_area_room_deferred_then_resolved_after_grid_loads(self) -> None:
        """A StartingArea naming a not-yet-imported room resolves once the grid loads."""
        export_grid_bundles(self.root)
        fixture_key = self.grid.taproom.fixture_key

        # Wipe the AUTHORED graph the export just captured (mirrors
        # GridImportTests.test_fresh_load_creates_graph) so the room the
        # StartingArea fixture below names does NOT exist yet when the
        # content-fixtures pass runs — only the grid bundle re-creates it.
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
        self.assertFalse(RoomProfile.objects.filter(fixture_key=fixture_key).exists())

        _write_starting_area_fixture(
            self.root,
            name="Arx City",
            description="The starting city.",
            room_key=fixture_key,
        )

        world_result = load_world_content(self.root)

        self.assertEqual(world_result.deferred_resolved, 1)
        self.assertEqual(world_result.skipped, [])
        self.assertEqual(world_result.created, 1)

        starting_area = StartingArea.objects.get(name="Arx City")
        self.assertIsNotNone(starting_area.default_starting_room)
        self.assertEqual(starting_area.default_starting_room.fixture_key, fixture_key)
        # The grid bundle itself landed too — the retry depended on it.
        self.assertTrue(RoomProfile.objects.filter(fixture_key=fixture_key).exists())

    def test_starting_area_missing_room_lands_in_skipped(self) -> None:
        """A room no bundle ever defines skips; every other fixture still loads."""
        _write(self.root, "skills/performance.md", GOOD_SKILL)
        _write_starting_area_fixture(
            self.root,
            name="Nowhere City",
            description="A city with no grid bundle.",
            room_key="nowhere/no-such-room",
        )

        world_result = load_world_content(self.root)

        self.assertEqual(len(world_result.skipped), 1)
        self.assertIn("nowhere/no-such-room", world_result.skipped[0])
        self.assertEqual(world_result.deferred_resolved, 0)
        self.assertFalse(StartingArea.objects.filter(name="Nowhere City").exists())
        # Everything else in the same run still loaded.
        self.assertTrue(Trait.objects.filter(name="Performance").exists())
        self.assertGreaterEqual(world_result.created, 1)


class RealBootstrapFallbackRoomTests(TestCase):
    """The REAL bootstrap path, not a hand-built grid fixture (#2448).

    ``ensure_canonical_fallback_room`` now houses its room in a reserved
    AUTHORED area (see ``world.seeds.character_creation``) specifically so this
    round-trip works on a fresh DB: without a home area, the room was AUTHORED
    but never visited by ``export_grid_bundles`` (which only walks rooms via
    AUTHORED areas), so a ``StartingArea`` naming it as ``default_starting_room``
    exported a fixture referencing a room no bundle contained — permanently
    ``skipped`` on reload, never resolved by the deferred retry.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_fallback_room_and_starting_area_survive_fresh_load(self) -> None:
        room = ensure_canonical_fallback_room()
        profile = room.room_profile
        area_pk = profile.area_id
        self.assertIsNotNone(area_pk, "fallback room must be housed in an area to export")

        starting_area = StartingArea.objects.create(
            name="Bootstrap City",
            description="The bootstrap starting area.",
            default_starting_room=profile,
        )

        export_to_content_repo(self.root)
        export_grid_bundles(self.root)

        # Wipe everything the export just captured — mirrors a fixtures-only
        # fresh DB where only the bundle/fixture files exist, not these rows.
        starting_area.delete()
        room.delete()  # cascades the RoomProfile row (OneToOne CASCADE)
        Area.objects.filter(pk=area_pk).delete()

        self.assertFalse(
            RoomProfile.objects.filter(fixture_key=FALLBACK_STARTING_ROOM_FIXTURE_KEY).exists()
        )
        self.assertFalse(StartingArea.objects.filter(name="Bootstrap City").exists())

        world_result = load_world_content(self.root)

        self.assertGreaterEqual(world_result.deferred_resolved, 1)
        self.assertEqual(world_result.skipped, [])

        recreated_area = StartingArea.objects.get(name="Bootstrap City")
        self.assertIsNotNone(recreated_area.default_starting_room)
        self.assertEqual(
            recreated_area.default_starting_room.fixture_key,
            FALLBACK_STARTING_ROOM_FIXTURE_KEY,
        )
