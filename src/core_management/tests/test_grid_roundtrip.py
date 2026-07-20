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

    def test_ambient_condition_group_derives_and_installs_trigger(self) -> None:
        from flows.models import Trigger
        from world.locations.constants import LocationParentType
        from world.narrative.constants import ConditionType
        from world.narrative.factories import AmbientEmoteConditionFactory, AmbientEmoteLineFactory
        from world.narrative.models import AmbientEmoteLine
        from world.species.factories import SpeciesFactory

        species = SpeciesFactory(name="Infernal")
        line = AmbientEmoteLineFactory(
            parent_type=LocationParentType.ROOM,
            room_profile=self.grid.taproom,
            area=None,
            bystander_body="A murmur runs through the taproom.",
        )
        AmbientEmoteConditionFactory(
            line=line, condition_type=ConditionType.SPECIES, species=species
        )

        export_to_content_repo(self.root)
        export_grid_bundles(self.root)

        # Drift: delete everything, confirm nothing exists before reimport.
        AmbientEmoteLine.objects.all().delete()
        self.assertFalse(Trigger.objects.filter(obj=self.grid.taproom_obj).exists())

        load_world_content(self.root)

        restored = AmbientEmoteLine.objects.get(
            room_profile=self.grid.taproom, bystander_body="A murmur runs through the taproom."
        )
        self.assertEqual(restored.conditions.count(), 1)
        self.assertEqual(restored.conditions.first().species.name, "Infernal")
        self.assertTrue(
            Trigger.objects.filter(obj=self.grid.taproom_obj).exists(),
            "importing ambient content should derive + install its condition-group Trigger",
        )

    def test_area_scoped_group_installs_on_rooms_without_room_override(self) -> None:
        from flows.models import Trigger
        from world.locations.constants import LocationParentType
        from world.narrative.factories import AmbientEmoteLineFactory

        AmbientEmoteLineFactory(
            parent_type=LocationParentType.AREA,
            area=self.grid.city,
            room_profile=None,
            arriver_body="The district's general mood.",
        )

        export_to_content_repo(self.root)
        export_grid_bundles(self.root)
        load_world_content(self.root)

        self.assertTrue(Trigger.objects.filter(obj=self.grid.taproom_obj).exists())
