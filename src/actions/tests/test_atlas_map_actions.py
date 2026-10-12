"""Tests for the staff world-map actions (#4242): one ``.run()`` success test per
action with plain-int kwargs (the REST dispatch shape) and one non-staff refusal."""

from __future__ import annotations

from django.test import TestCase
from evennia.objects.models import ObjectDB

from actions.definitions.atlas_map import (
    AtlasCarveFootprintAction,
    AtlasCreateRegionMapAction,
    AtlasPaintTerrainAction,
)
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.areas.tests.test_worldmap import tiny_map
from world.areas.worldmap.constants import PipSource, Terrain
from world.areas.worldmap.models import AreaFootprintPip, RegionMap, TerrainPip
from world.areas.worldmap.services import create_region_map, import_region_map_file


def _actor(db_key: str, *, staff: bool) -> ObjectDB:
    char = CharacterFactory(db_key=db_key)
    account = AccountFactory(username=f"acct_{db_key}", is_staff=staff)
    char.db_account = account
    char.save()
    return char


class AtlasMapActionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = _actor("MapStaff", staff=True)
        cls.player = _actor("MapPlayer", staff=False)
        cls.region = create_region_map(name="Testland", anchor_x=0, anchor_y=0, width_cells=2)
        import_region_map_file(region=cls.region, file_name="t.map", data=tiny_map().encode())
        cls.county = AreaFactory(name="County", level=AreaLevel.COUNTY)

    def test_player_is_refused(self) -> None:
        result = AtlasCarveFootprintAction().run(self.player, area_id=self.county.pk, add=[[1, 1]])
        assert not result.success

    def test_create_region_map(self) -> None:
        result = AtlasCreateRegionMapAction().run(
            self.staff, name="Eastland", anchor_x=2, anchor_y=0, width_cells=3
        )
        assert result.success, result.message
        region = RegionMap.objects.get(pk=result.data["region_id"])
        assert region.width_cells == 3
        assert region.created_by == self.staff.db_account
        refused = AtlasCreateRegionMapAction().run(
            self.staff, name="Overlap", anchor_x=1, anchor_y=0, width_cells=2
        )
        assert not refused.success

    def test_carve_and_shrink(self) -> None:
        result = AtlasCarveFootprintAction().run(
            self.staff, area_id=self.county.pk, add=[[1, 1], [2, 1]]
        )
        assert result.success, result.message
        assert result.data == {"area_id": self.county.pk, "added": 2, "removed": 0}
        result = AtlasCarveFootprintAction().run(
            self.staff, area_id=self.county.pk, remove=[[1, 1]]
        )
        assert result.success
        assert AreaFootprintPip.objects.filter(area=self.county).count() == 1
        refused = AtlasCarveFootprintAction().run(
            self.staff, area_id=self.county.pk, add=[[15, 15]]
        )
        assert not refused.success
        assert "water" in refused.message
        bad = AtlasCarveFootprintAction().run(self.staff, area_id=self.county.pk, add="nope")
        assert not bad.success

    def test_paint_terrain(self) -> None:
        result = AtlasPaintTerrainAction().run(
            self.staff, region_id=self.region.pk, pips=[[3, 3]], terrain="marsh"
        )
        assert result.success, result.message
        pip = TerrainPip.objects.get(x=3, y=3)
        assert pip.terrain == Terrain.MARSH
        assert pip.source == PipSource.STAFF
        refused = AtlasPaintTerrainAction().run(
            self.staff, region_id=self.region.pk, pips=[[3, 3]], terrain="lava"
        )
        assert not refused.success
