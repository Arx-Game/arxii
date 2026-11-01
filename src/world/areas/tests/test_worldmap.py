"""The world map (#4242): the generator-file rasterizer, the region and footprint
services, and the staff API.

The rasterizer is exercised on a hand-written three-field generator file (the
parse path) and, when the real Catenys map is on disk, on that file too. The
services are exercised on a two-cell region.
"""

from __future__ import annotations

import gzip
import json
import os
from pathlib import Path

from django.test import TestCase, tag
from django.urls import reverse
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.areas.models import Area
from world.areas.worldmap.azgaar import (
    MapFileError,
    flatten_path,
    parse_map,
    rasterize,
    terrain_for,
)
from world.areas.worldmap.constants import PipSource, Terrain
from world.areas.worldmap.models import (
    AreaFootprintPip,
    RegionMap,
    RegionMapUpload,
    TerrainPip,
)
from world.areas.worldmap.services import (
    WorldMapServiceError,
    create_region_map,
    footprint_of,
    holder_at,
    import_region_map_file,
    paint_terrain,
    region_read,
    set_footprint,
)

CATENYS_MAP = Path(os.environ.get("ARXII_CATENYS_MAP", "/home/vscode/catenys-maps/round3/C1.map"))


def tiny_map(
    *,
    width_px: int = 40,
    height_px: int = 40,
    spacing: float = 10.0,
    heights: list[int] | None = None,
    river: str = "",
) -> str:
    """A generator file of a 4 by 4 grid: the left half land, the right half sea,
    a lake in one land cell, a river down the second column when asked."""
    cells_x = cells_y = 4
    n = cells_x * cells_y
    if heights is None:
        heights = [30 if (i % cells_x) < 2 else 5 for i in range(n)]
        heights[5] = 10  # a lake cell in the land half
    features = [
        0,
        {"i": 1, "type": "ocean", "land": False},
        {"i": 2, "type": "lake", "land": False},
    ]
    feature_ids = [2 if i == 5 else (1 if h < 20 else 0) for i, h in enumerate(heights)]
    prec = [2] * n  # moisture 6: grassland, so land reads as plain
    temp = [12] * n
    svg = (
        '<svg id="map" width="40" height="40">\n<g id="rivers" fill="#5d97bb">'
        + (f'<path id="river1" d="{river}"/>' if river else "")
        + "</g>\n</svg>"
    )
    grid = json.dumps(
        {"spacing": spacing, "cellsX": cells_x, "cellsY": cells_y, "boundary": [], "points": []}
    )
    fields = [
        "1.154.0|File can be loaded in azgaar.github.io/Fantasy-Map-Generator|2026-10-12|7"
        f"|{width_px}|{height_px}|1",
        json.dumps({"seed": "7"}),
        "",
        "[]",
        "",
        svg,
        grid,
        ",".join(map(str, heights)),
        ",".join(map(str, prec)),
        ",".join(map(str, feature_ids)),
        ",".join(["0"] * n),
        ",".join(map(str, temp)),
        json.dumps(features),
        "[]",
    ]
    return "\r\n".join(fields)


class RasterizerTests(TestCase):
    def test_parses_a_tiny_map_and_rasterizes_land_sea_lake_and_river(self) -> None:
        gmap = parse_map(tiny_map(river="M15,0 L15,40"))
        assert gmap.cells_x == 4
        assert gmap.width_px == 40
        assert gmap.lake_feature_ids == frozenset({2})
        assert len(gmap.river_paths) == 1
        pips = rasterize(gmap, width_cells=2, height_cells=2)  # 20 by 20 pips, 2 px each
        assert len(pips) == 400
        by = {(p.x, p.y): p for p in pips}
        assert by[(2, 2)].terrain == Terrain.PLAIN  # land, dryish, warm enough
        assert by[(15, 15)].terrain == Terrain.WATER
        assert by[(7, 7)].terrain == Terrain.LAKE  # grid cell 5 = column 1, row 1
        assert by[(7, 2)].has_river  # the river runs down x=15px -> pip column 7
        assert not by[(2, 2)].has_river

    def test_terrain_bands(self) -> None:
        assert terrain_for(10, 12, 9, is_lake=False) == Terrain.WATER
        assert terrain_for(10, 12, 9, is_lake=True) == Terrain.LAKE
        assert terrain_for(75, 12, 9, is_lake=False) == Terrain.MOUNTAIN
        assert terrain_for(60, 12, 9, is_lake=False) == Terrain.HILL
        assert terrain_for(30, 12, 2, is_lake=False) == Terrain.DESERT
        assert terrain_for(30, 12, 12, is_lake=False) == Terrain.FOREST
        assert terrain_for(30, -8, 12, is_lake=False) == Terrain.GLACIER
        assert terrain_for(30, 0, 7, is_lake=False) == Terrain.FOREST  # taiga reads as forest

    def test_flattens_cubic_paths(self) -> None:
        pts = flatten_path("M0,0C0,0,10,0,10,10")
        assert pts[0] == (0.0, 0.0)
        assert pts[-1] == (10.0, 10.0)
        assert len(pts) == 9

    def test_refuses_a_file_that_is_not_a_map(self) -> None:
        with self.assertRaises(MapFileError):
            parse_map("hello|world")
        with self.assertRaises(MapFileError):
            parse_map("1.0|File can be loaded|d|s|100|100|1\r\nsettings\r\nno grid here")

    @tag("slow")
    def test_the_catenys_map_rasterizes_with_its_rivers(self) -> None:
        if not CATENYS_MAP.exists():
            self.skipTest("the Catenys map file is not on this machine")
        gmap = parse_map(CATENYS_MAP.read_text(encoding="utf-8"))
        pips = rasterize(gmap, 20, 20)
        water = sum(p.terrain in (Terrain.WATER, Terrain.LAKE) for p in pips)
        rivers = sum(p.has_river for p in pips)
        assert 15000 < water < 22000
        assert rivers > 3000
        # the Radiant's mouth on the Chain, from the map's own site list: pip (102, 103)
        by = {(p.x, p.y): p for p in pips}
        assert any(by[(x, y)].has_river for x in range(100, 104) for y in range(102, 106))


class RegionServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(username="mapstaff", is_staff=True)
        cls.region = create_region_map(
            name="Testland", anchor_x=5, anchor_y=3, width_cells=2, actor=cls.staff
        )

    def test_create_refuses_blank_and_overlap(self) -> None:
        with self.assertRaises(WorldMapServiceError):
            create_region_map(name="  ", anchor_x=0, anchor_y=0, width_cells=2)
        import_region_map_file(region=self.region, file_name="t.map", data=tiny_map().encode())
        with self.assertRaises(WorldMapServiceError):
            create_region_map(name="Overlap", anchor_x=6, anchor_y=3, width_cells=2)
        beside = create_region_map(name="Beside", anchor_x=7, anchor_y=3, width_cells=2)
        assert beside.pip_x0 == 70

    def test_new_continent_creates_the_rung_once_and_links_it(self) -> None:
        first = create_region_map(
            name="Catenys", anchor_x=20, anchor_y=0, width_cells=2, new_continent=True
        )
        continent = first.area
        assert continent is not None
        assert continent.level == AreaLevel.CONTINENT
        assert continent.slug == "catenys"
        assert continent.parent is None
        # a continent already on the ladder is linked, never twinned
        staged = AreaFactory(name="Luxen", slug="luxen", level=AreaLevel.CONTINENT)
        again = create_region_map(
            name="luxen", anchor_x=30, anchor_y=0, width_cells=2, new_continent=True
        )
        assert again.area_id == staged.pk
        assert Area.objects.filter(level=AreaLevel.CONTINENT).count() == 2
        # a slug another area holds refuses the whole placement
        AreaFactory(name="Umbros", slug="umbros", level=AreaLevel.KINGDOM)
        with self.assertRaises(WorldMapServiceError):
            create_region_map(
                name="Umbros", anchor_x=40, anchor_y=0, width_cells=2, new_continent=True
            )
        assert not RegionMap.objects.filter(name="Umbros").exists()

    def test_upload_rasterizes_to_world_pips_and_keeps_the_file(self) -> None:
        upload = import_region_map_file(
            region=self.region, file_name="t.map", data=tiny_map().encode(), actor=self.staff
        )
        self.region.refresh_from_db()
        assert self.region.height_cells == 2
        assert upload.rasterized_at is not None
        assert upload.source_width_px == 40
        assert gzip.decompress(bytes(upload.file_bytes)).decode() == tiny_map()
        assert TerrainPip.objects.filter(region=self.region).count() == 400
        pip = TerrainPip.objects.get(x=50 + 15, y=30 + 15)
        assert pip.terrain == Terrain.WATER
        assert pip.source == PipSource.GENERATOR

    def test_a_bad_file_writes_nothing(self) -> None:
        with self.assertRaises(WorldMapServiceError):
            import_region_map_file(region=self.region, file_name="x.map", data=b"not a map")
        assert not RegionMapUpload.objects.exists()
        assert not TerrainPip.objects.exists()

    def test_staff_paint_survives_a_second_upload(self) -> None:
        import_region_map_file(region=self.region, file_name="t.map", data=tiny_map().encode())
        painted = paint_terrain(region=self.region, pips=[(52, 32), (53, 32)], terrain="marsh")
        assert painted == 2
        import_region_map_file(region=self.region, file_name="t2.map", data=tiny_map().encode())
        assert TerrainPip.objects.get(x=52, y=32).terrain == Terrain.MARSH
        assert TerrainPip.objects.get(x=52, y=32).source == PipSource.STAFF
        assert TerrainPip.objects.get(x=51, y=32).source == PipSource.GENERATOR
        assert TerrainPip.objects.filter(region=self.region).count() == 400
        assert RegionMapUpload.objects.filter(region=self.region).count() == 2
        with self.assertRaises(WorldMapServiceError):
            paint_terrain(region=self.region, pips=[(0, 0)], terrain="marsh")
        with self.assertRaises(WorldMapServiceError):
            paint_terrain(region=self.region, pips=[(52, 32)], terrain="lava")


class FootprintServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.region = create_region_map(name="Testland", anchor_x=0, anchor_y=0, width_cells=2)
        import_region_map_file(region=cls.region, file_name="t.map", data=tiny_map().encode())
        cls.kingdom = AreaFactory(name="Kingdom", level=AreaLevel.KINGDOM)
        cls.county = AreaFactory(name="County", level=AreaLevel.COUNTY, parent=cls.kingdom)
        cls.barony = AreaFactory(name="Barony", level=AreaLevel.BARONY, parent=cls.county)

    def test_carve_grow_and_shrink_with_one_holder_per_pip(self) -> None:
        change = set_footprint(area=self.county, add=[(1, 1), (2, 1), (1, 2)])
        assert (change.added, change.removed, change.skipped) == (3, 0, 0)
        # carving the barony moves the county's row down; the county's footprint still has it
        set_footprint(area=self.barony, add=[(2, 1)])
        assert holder_at(2, 1) == self.barony
        assert holder_at(1, 1) == self.county
        assert holder_at(9, 9) is None
        assert footprint_of(self.county) == {(1, 1), (2, 1), (1, 2)}
        assert AreaFootprintPip.objects.filter(x=2, y=1).count() == 1
        # a barony claiming open ground grows the county with it: containment by construction
        set_footprint(area=self.barony, add=[(2, 7)])
        assert footprint_of(self.county) >= {(2, 7)}
        # the county cannot take back a pip its barony stands on: the drag skips it (#4317)
        change = set_footprint(area=self.county, remove=[(2, 1), (1, 1)])
        assert (change.removed, change.skipped, change.skipped_holders) == (1, 1, ("Barony",))
        assert holder_at(2, 1) == self.barony
        assert holder_at(1, 1) == self.kingdom
        # shrinking the barony hands the pip back to the county
        change = set_footprint(area=self.barony, remove=[(2, 7)])
        assert (change.added, change.removed) == (0, 1)
        assert holder_at(2, 7) == self.county
        # shrinking the county hands its own pip to the kingdom above it
        change = set_footprint(area=self.county, remove=[(1, 2)])
        assert (change.added, change.removed) == (0, 1)
        assert holder_at(1, 2) == self.kingdom
        # another domain's pip is skipped, not refused, and the rest of the drag lands (#4317)
        other = AreaFactory(name="Other", level=AreaLevel.COUNTY, parent=self.kingdom)
        change = set_footprint(area=other, add=[(2, 1), (2, 7), (5, 5)])
        assert (change.added, change.skipped) == (1, 2)
        assert change.skipped_holders == ("Barony", "County")
        assert holder_at(5, 5) == other
        assert holder_at(2, 1) == self.barony
        # water is taken like land: a realm's footprint includes its waters (ruling, #4317)
        change = set_footprint(area=self.county, add=[(15, 15)])
        assert change.added == 1
        assert holder_at(15, 15) == self.county
        # a ward has no footprint
        ward = AreaFactory(name="Ward", level=AreaLevel.WARD, parent=self.barony)
        with self.assertRaises(WorldMapServiceError):
            set_footprint(area=ward, add=[(2, 1)])

    def test_region_read_groups_footprints_with_holder_and_seat(self) -> None:
        set_footprint(area=self.county, add=[(1, 1), (2, 1)])
        set_footprint(area=self.barony, add=[(2, 1)])
        read = region_read(self.region)
        assert len(read.pips) == 400
        names = [f.name for f in read.footprints]
        assert names == ["Barony", "County", "Kingdom"]  # the ancestors are derived
        county = next(f for f in read.footprints if f.name == "County")
        assert county.pips == [(1, 1), (2, 1)]
        assert county.seat == (2, 1)
        assert county.holder_org_id is None

    def test_carve_reports_each_pips_prior_and_new_holder(self) -> None:
        set_footprint(area=self.kingdom, add=[(3, 3)])
        change = set_footprint(area=self.county, add=[(3, 3), (4, 3)])
        assert sorted(change.changed) == [
            (3, 3, self.kingdom.pk, self.county.pk),
            (4, 3, None, self.county.pk),
        ]
        change = set_footprint(area=self.county, remove=[(3, 3)])
        assert change.changed == ((3, 3, self.county.pk, self.kingdom.pk),)
        change = set_footprint(area=self.kingdom, remove=[(3, 3)])
        assert change.changed == ((3, 3, self.kingdom.pk, None),)
        # a pip already inside and a skipped pip are not changes
        other = AreaFactory(name="Other2", level=AreaLevel.COUNTY, parent=self.kingdom)
        change = set_footprint(area=other, add=[(4, 3)])
        assert change.changed == ()


class RegionMapApiTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(username="apistaff", is_staff=True)
        cls.player = AccountFactory(username="apiplayer", is_staff=False)
        cls.region = create_region_map(name="Testland", anchor_x=0, anchor_y=0, width_cells=2)

    def test_non_staff_are_refused(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.player)
        assert client.get(reverse("world_builder:region-map-list")).status_code == 403

    def test_upload_pips_and_download(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.staff)
        from django.core.files.uploadedfile import SimpleUploadedFile

        upload = SimpleUploadedFile("tiny.map", tiny_map().encode(), content_type="text/plain")
        res = client.post(
            reverse("world_builder:region-map-upload", args=[self.region.pk]),
            {"file": upload},
            format="multipart",
        )
        assert res.status_code == 201, res.content
        assert res.json()["pip_count"] == 400
        res = client.get(reverse("world_builder:region-map-pips", args=[self.region.pk]))
        assert res.status_code == 200
        body = res.json()
        assert body["region"]["height_cells"] == 2
        assert len(body["pips"]) == 400
        assert body["footprints"] == []
        res = client.get(reverse("world_builder:region-map-file", args=[self.region.pk]))
        assert res.status_code == 200
        assert res["Content-Disposition"].endswith('"tiny.map"')
        assert res.content.decode() == tiny_map()
        bad = SimpleUploadedFile("bad.map", b"nope", content_type="text/plain")
        res = client.post(
            reverse("world_builder:region-map-upload", args=[self.region.pk]),
            {"file": bad},
            format="multipart",
        )
        assert res.status_code == 400
