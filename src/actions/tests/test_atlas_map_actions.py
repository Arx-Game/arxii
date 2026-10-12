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
from world.character_creation.factories import RealmFactory
from world.societies.houses.almanach import plant_rung
from world.societies.houses.constants import TitleTier


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

    def test_staff_place_a_region_from_the_website_with_their_character_out_of_the_world(
        self,
    ) -> None:
        """The production failure on #4317: every world-builder action is dispatched over
        REST as the account's browsing character, which nobody is puppeting, so
        ``character.account`` is empty and the staff gate used to answer "Staff only."."""
        from django.urls import reverse
        from rest_framework.test import APIClient

        from world.character_sheets.factories import CharacterSheetFactory
        from world.roster.factories import grant_test_tenure

        account = AccountFactory(username="apostate_on_the_web", is_staff=True)
        character = CharacterFactory(db_key="Apostate")
        grant_test_tenure(CharacterSheetFactory(character=character), account)
        assert character.account is None
        client = APIClient()
        client.force_authenticate(user=account)
        response = client.post(
            reverse("actions:dispatch-action", kwargs={"character_id": character.pk}),
            {
                "ref": {"backend": "registry", "registry_key": "atlas_create_region_map"},
                "kwargs": {"name": "Catenys", "anchor_x": 40, "anchor_y": 0, "width_cells": 20},
            },
            format="json",
        )
        assert response.status_code == 200, response.content
        assert response.json()["success"] is True, response.json()
        assert RegionMap.objects.filter(name="Catenys").exists()

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

    def test_create_region_map_with_a_new_continent(self) -> None:
        result = AtlasCreateRegionMapAction().run(
            self.staff, name="Catenys", anchor_x=20, anchor_y=0, width_cells=2, new_continent=True
        )
        assert result.success, result.message
        region = RegionMap.objects.get(pk=result.data["region_id"])
        assert region.area is not None
        assert region.area.name == "Catenys"
        assert region.area.level == AreaLevel.CONTINENT

    def test_carve_and_shrink(self) -> None:
        result = AtlasCarveFootprintAction().run(
            self.staff, area_id=self.county.pk, add=[[1, 1], [2, 1]]
        )
        assert result.success, result.message
        assert result.data == {"area_id": self.county.pk, "added": 2, "removed": 0, "skipped": 0}
        result = AtlasCarveFootprintAction().run(
            self.staff, area_id=self.county.pk, remove=[[1, 1]]
        )
        assert result.success
        assert AreaFootprintPip.objects.filter(area=self.county).count() == 1
        # water is taken like land (#4317)
        wet = AtlasCarveFootprintAction().run(self.staff, area_id=self.county.pk, add=[[15, 15]])
        assert wet.success, wet.message
        assert wet.data["added"] == 1
        # a neighbour's pip is skipped and named, and the rest of the drag lands (#4317)
        other = AreaFactory(name="Other", level=AreaLevel.COUNTY)
        partial = AtlasCarveFootprintAction().run(
            self.staff, area_id=other.pk, add=[[2, 1], [3, 1]]
        )
        assert partial.success, partial.message
        assert partial.data == {"area_id": other.pk, "added": 1, "removed": 0, "skipped": 1}
        assert partial.message == "Other: 1 pips added, 0 removed. 1 skipped (County)."
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

    def test_carve_by_title_walks_to_the_rungs_own_area(self) -> None:
        realm = RealmFactory(name="Luxen")
        county = plant_rung(realm=realm, tier=TitleTier.COUNTY, name="Salvation")
        result = AtlasCarveFootprintAction().run(
            self.staff, title_id=county.pk, add=[[1, 1], [2, 1]]
        )
        assert result.success, result.message
        area = AreaFootprintPip.objects.get(x=1, y=1).area
        assert area.level == AreaLevel.COUNTY
        assert area.name == "Salvation"
        missing = AtlasCarveFootprintAction().run(self.staff, title_id=999999, add=[[1, 1]])
        assert not missing.success
