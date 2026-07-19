"""Full export -> mutate -> import journey test for the grid pipeline (#2436/#2448).

``test_grid_export.py``/``test_grid_import.py`` cover each half of the pipeline in
isolation; ``test_load_sequencing.py`` (Task 5) covers the ``StartingArea`` ->
grid-bundle deferral edge case specifically. This file's distinct value is the full
round trip through the real public entry points — ``export_to_content_repo`` +
``export_grid_bundles`` write what a live game would write, then
``load_world_content`` reads it back into a DB that has since drifted — proving the
whole pipeline is a fixed point: export -> mutate -> reload always converges back
to the exported state, never duplicating or losing rows.
"""

from __future__ import annotations

from pathlib import Path
import tempfile

from django.test import TestCase
from evennia.objects.models import ObjectDB

from core_management.content_export import export_to_content_repo
from core_management.content_fixtures import load_world_content
from core_management.grid_export import export_grid_bundles
from core_management.tests._grid_fixtures import build_sample_grid
from evennia_extensions.models import ObjectDisplayData
from world.areas.models import Area
from world.character_creation.models import StartingArea
from world.clues.models import RoomClue
from world.magic.models import PortalAnchor

_ROOM_TYPECLASS = "typeclasses.rooms.Room"


class GridRoundTripJourneyTests(TestCase):
    """Export the authored grid + a StartingArea, mutate the DB, reload, compare."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.grid = build_sample_grid()
        cls.starting_area = StartingArea.objects.create(
            name="Arx",
            description="The city where every story begins.",
            default_starting_room=cls.grid.taproom,
        )

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_export_mutate_reload_converges_to_exported_state(self) -> None:
        """export -> mutate DB -> load_world_content -> DB matches the export again."""
        original_description = ObjectDisplayData.objects.get(
            object=self.grid.taproom_obj
        ).permanent_description
        original_city_name = self.grid.city.name
        fixture_key = self.grid.taproom.fixture_key
        clue_fixture_key = self.grid.room_clue.fixture_key
        anchor_fixture_key = self.grid.portal_anchor.fixture_key
        room_count_before = ObjectDB.objects.filter(db_typeclass_path=_ROOM_TYPECLASS).count()

        export_to_content_repo(self.root)
        export_grid_bundles(self.root)

        # Drift the DB away from what was just exported.
        display = ObjectDisplayData.objects.get(object=self.grid.taproom_obj)
        display.permanent_description = "A ruin, long abandoned."
        display.save()
        self.grid.city.name = "Somewhere Else"
        self.grid.city.save()
        self.grid.room_clue.detect_difficulty = 1
        self.grid.room_clue.save()

        world_result = load_world_content(self.root)

        self.assertEqual(world_result.skipped, [])

        # Room description restored to the exported value, same ObjectDB row.
        restored_display = ObjectDisplayData.objects.get(object=self.grid.taproom_obj)
        self.assertEqual(restored_display.permanent_description, original_description)

        # Area name restored, same Area row (looked up by slug, not recreated).
        restored_city = Area.objects.get(slug=self.grid.city.slug)
        self.assertEqual(restored_city.name, original_city_name)
        self.assertEqual(restored_city.pk, self.grid.city.pk)

        # StartingArea -> room link survives the round trip intact.
        restored_starting_area = StartingArea.objects.get(name="Arx")
        self.assertIsNotNone(restored_starting_area.default_starting_room)
        self.assertEqual(restored_starting_area.default_starting_room.fixture_key, fixture_key)
        self.assertEqual(restored_starting_area.default_starting_room_id, self.grid.taproom.pk)

        restored_clue = RoomClue.objects.get(fixture_key=clue_fixture_key)
        self.assertEqual(restored_clue.detect_difficulty, 5)
        self.assertTrue(
            PortalAnchor.objects.active().filter(fixture_key=anchor_fixture_key).exists()
        )

        # No duplicate rooms were created by the reload.
        room_count_after = ObjectDB.objects.filter(db_typeclass_path=_ROOM_TYPECLASS).count()
        self.assertEqual(room_count_after, room_count_before)

    def test_ambient_line_round_trips_and_installs_trigger(self) -> None:
        from flows.models import Trigger
        from world.narrative.ambient_trigger_content import ensure_ambient_reaction_content
        from world.narrative.factories import AmbientEmoteLineFactory
        from world.narrative.models import AmbientEmoteLine

        ensure_ambient_reaction_content()
        line = AmbientEmoteLineFactory(
            room_profile=self.grid.taproom,
            area=None,
            arriver_body="The taproom's low murmur greets you.",
            weight=3,
            fire_chance=75,
            cooldown_minutes=30,
            is_active=False,
        )

        export_to_content_repo(self.root)
        export_grid_bundles(self.root)

        # Drift: delete the line entirely, and confirm no Trigger exists yet.
        AmbientEmoteLine.objects.filter(pk=line.pk).delete()
        self.assertFalse(Trigger.objects.filter(obj=self.grid.taproom_obj).exists())

        load_world_content(self.root)

        restored = AmbientEmoteLine.objects.get(
            room_profile=self.grid.taproom, arriver_body="The taproom's low murmur greets you."
        )
        self.assertIsNotNone(restored.pk)
        self.assertEqual(restored.weight, 3)
        self.assertEqual(restored.fire_chance, 75)
        self.assertEqual(restored.cooldown_minutes, 30)
        self.assertEqual(restored.trigger_type, line.trigger_type)
        self.assertFalse(restored.is_active)
        self.assertTrue(
            Trigger.objects.filter(obj=self.grid.taproom_obj).exists(),
            "importing an authored room with ambient content should install its Trigger",
        )

    def test_ambient_area_fallback_installs_trigger_on_every_room(self) -> None:
        """An area-scoped line with no room-scoped lines installs Triggers on every room
        in that area's bundle (the ``area_has_lines`` fallback branch in
        ``core_management.grid_import._import_ambient_lines``), not just rooms with a
        direct ``AmbientEmoteLine`` of their own."""
        from flows.models import Trigger
        from world.locations.constants import LocationParentType
        from world.narrative.ambient_trigger_content import ensure_ambient_reaction_content
        from world.narrative.factories import AmbientEmoteLineFactory

        ensure_ambient_reaction_content()
        AmbientEmoteLineFactory(
            parent_type=LocationParentType.AREA,
            area=self.grid.city,
            room_profile=None,
            arriver_body="A general hum of city life surrounds you.",
        )

        export_to_content_repo(self.root)
        export_grid_bundles(self.root)

        # No room in the bundle has a Trigger yet — the fallback line hasn't imported.
        self.assertFalse(Trigger.objects.filter(obj=self.grid.taproom_obj).exists())

        load_world_content(self.root)

        self.assertTrue(
            Trigger.objects.filter(obj=self.grid.taproom_obj).exists(),
            "an area-scoped fallback ambient line should install a Trigger on every "
            "room in that area's bundle, even a room with no direct AmbientEmoteLine",
        )
