"""The world map (#4242): the generator-file rasterizer, the region and footprint
services, and the staff API.

The rasterizer is exercised on a hand-written three-field generator file (the
parse path) and, when the real Catenys map is on disk, on that file too. The
services are exercised on a two-cell region.
"""

from __future__ import annotations

import gzip
from itertools import pairwise
import json
import os
from pathlib import Path
from unittest import mock

from django.test import TestCase, tag
from django.urls import reverse
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.areas.models import Area
from world.areas.worldmap.azgaar import (
    GeneratorRiver,
    MapFileError,
    flatten_path,
    parse_map,
    rasterize,
    river_chain,
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
    MAX_FOOTPRINT_PIPS_PER_CALL,
    WorldMapServiceError,
    _rows_at,
    clear_footprint,
    create_region_map,
    footprint_of,
    holder_at,
    import_region_map_file,
    paint_river,
    paint_terrain,
    region_read,
    reset_rivers,
    restore_pips,
    set_footprint,
)

CATENYS_MAP = Path(os.environ.get("ARXII_CATENYS_MAP", "/home/vscode/catenys-maps/round3/C1.map"))


def tiny_map(  # noqa: PLR0913 - a fixture file's knobs
    *,
    width_px: int = 40,
    height_px: int = 40,
    spacing: float = 10.0,
    heights: list[int] | None = None,
    river: str = "",
    rivers: list[tuple[int, str, float, int]] | None = None,
    records: bool = True,
    precipitation: int = 2,
) -> str:
    """A generator file of a 4 by 4 grid: the left half land, the right half sea,
    a lake in one land cell, a river down the second column when asked.

    ``river`` is one main stem's outline; ``rivers`` is any number as ``(id,
    outline, length, parent id)``. An outline runs from the mouth up one bank and
    back down the other, the way the generator writes it. ``records=False``
    leaves out the river records, as an older generator's file would.
    """
    if river:
        rivers = [(1, river, 50.0, 0)]
    rivers = rivers or []
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
    prec = [precipitation] * n  # 2 is moisture 6: grassland, so land reads as plain
    temp = [12] * n
    svg = (
        '<svg id="map" width="40" height="40">\n<g id="rivers" fill="#5d97bb">'
        + "".join(f'<path id="river{i}" d="{d}"/>' for i, d, _length, _parent in rivers)
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
    if rivers and records:
        fields.append(
            json.dumps(
                [
                    {"i": i, "mouth": 0, "length": length, "parent": parent}
                    for i, _d, length, parent in rivers
                ]
            )
        )
    return "\r\n".join(fields)


# Outlines for the river tests, on the tiny map's land half (pips 0-9 across; the
# lake is pips 5-9 across and down). Each runs mouth, source, mouth.
LONG_RIVER = "M15,40 L15,0 L15,40"  # pip column 7, top to bottom
SHORT_RIVER = "M3,38 L3,22 L3,38"  # pip column 1, rows 11 to 19
STREAM_INTO_SHORT = "M3,25 L9,25 L3,25"  # pip row 12, from column 4 west to column 1
THREE_RIVERS = [
    (1, LONG_RIVER, 50.0, 0),
    (2, SHORT_RIVER, 10.0, 0),
    (3, STREAM_INTO_SHORT, 5.0, 2),
]


class RasterizerTests(TestCase):
    def test_parses_a_tiny_map_and_rasterizes_land_sea_lake_and_river(self) -> None:
        gmap = parse_map(tiny_map(river=LONG_RIVER))
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
        assert not by[(7, 7)].has_river  # it crosses the lake; water carries no river

    def test_only_the_longest_main_stems_become_river_pips(self) -> None:
        """#5189: a tributary and a short stem are streams the map does not draw,
        however long the tributary is."""
        streams = [
            (1, LONG_RIVER, 50.0, 0),
            (2, SHORT_RIVER, 10.0, 0),
            (3, STREAM_INTO_SHORT, 99.0, 2),
        ]
        gmap = parse_map(tiny_map(rivers=streams))
        with mock.patch("world.areas.worldmap.azgaar.MAJOR_RIVER_COUNT", 1):
            by = {(p.x, p.y): p for p in rasterize(gmap, width_cells=2, height_cells=2)}
        assert by[(7, 2)].has_river
        assert not by[(1, 15)].has_river  # the short stem
        assert not by[(3, 12)].has_river  # the tributary

    def test_a_stream_that_is_not_drawn_still_wets_the_ground(self) -> None:
        """#5189 changes which rivers are drawn, never the terrain: with enough rain
        that a river's moisture turns plain to forest, the ground under a stream
        the map does not draw is forest all the same."""
        gmap = parse_map(tiny_map(rivers=THREE_RIVERS, precipitation=4))
        with mock.patch("world.areas.worldmap.azgaar.MAJOR_RIVER_COUNT", 1):
            by = {(p.x, p.y): p for p in rasterize(gmap, width_cells=2, height_cells=2)}
        assert not by[(1, 15)].has_river
        assert by[(1, 15)].terrain == Terrain.FOREST
        assert by[(3, 3)].terrain == Terrain.PLAIN  # off every river

    def test_a_file_without_river_records_draws_no_river(self) -> None:
        gmap = parse_map(tiny_map(river=LONG_RIVER, records=False, precipitation=4))
        by = {(p.x, p.y): p for p in rasterize(gmap, width_cells=2, height_cells=2)}
        assert gmap.rivers == ()
        assert not any(p.has_river for p in by.values())
        assert by[(7, 2)].terrain == Terrain.FOREST  # the path still wets the ground

    def test_a_rivers_course_is_one_pip_wide_from_source_to_mouth(self) -> None:
        """The outline's two banks are four pixels apart, two pips; the course is
        the line between them, and no pip of it sits beside a pip two steps on."""
        river = GeneratorRiver(river_id=1, length=40.0, parent_id=0, path="M10,38 L3,2 L7,2 L14,38")
        chain = river_chain(river, 2.0, 20, 20)
        assert chain[0] == (2, 1)  # midway between the banks at the source
        assert chain[-1] == (6, 19)
        assert len(set(chain)) == len(chain)
        for before, after in pairwise(chain):
            assert max(abs(before[0] - after[0]), abs(before[1] - after[1])) == 1
        for before, after in zip(chain, chain[2:], strict=False):
            assert max(abs(before[0] - after[0]), abs(before[1] - after[1])) > 1

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
        assert 300 < rivers < 1200  # the twenty longest, not every stream (#5189)
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


class RiverServiceTests(TestCase):
    """#5189: rivers are drawn by hand, kept across uploads, and reset from the file.
    The region sits at cell (5, 3), so a file pip (x, y) is world pip (50 + x, 30 + y)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.region = create_region_map(name="Riverland", anchor_x=5, anchor_y=3, width_cells=2)

    def _upload(self) -> None:
        with mock.patch("world.areas.worldmap.azgaar.MAJOR_RIVER_COUNT", 1):
            import_region_map_file(
                region=self.region, file_name="t.map", data=tiny_map(rivers=THREE_RIVERS).encode()
            )

    def _reset(self) -> int:
        with mock.patch("world.areas.worldmap.azgaar.MAJOR_RIVER_COUNT", 1):
            return reset_rivers(region=self.region)

    def _has_river(self, x: int, y: int) -> bool:
        return TerrainPip.objects.get(x=50 + x, y=30 + y).has_river

    def test_a_river_is_drawn_and_erased_without_touching_the_ground(self) -> None:
        self._upload()
        # two land pips and one sea pip: the sea pip is passed over
        drawn = paint_river(region=self.region, pips=[(52, 32), (53, 32), (65, 45)], river=True)
        assert drawn == 2
        pip = TerrainPip.objects.get(x=52, y=32)
        assert pip.has_river
        assert pip.terrain == Terrain.PLAIN
        assert pip.source == PipSource.GENERATOR
        assert not TerrainPip.objects.get(x=65, y=45).has_river
        assert paint_river(region=self.region, pips=[(52, 32)], river=True) == 0
        assert paint_river(region=self.region, pips=[(52, 32), (53, 32)], river=False) == 2
        assert not TerrainPip.objects.get(x=52, y=32).has_river
        with self.assertRaises(WorldMapServiceError):
            paint_river(region=self.region, pips=[(0, 0)], river=True)

    def test_a_second_upload_keeps_rivers_as_staff_left_them(self) -> None:
        self._upload()
        assert self._has_river(7, 2)
        paint_river(region=self.region, pips=[(57, 32)], river=False)
        paint_river(region=self.region, pips=[(52, 33)], river=True)
        self._upload()
        assert not self._has_river(7, 2)  # erased by hand, and the file does not put it back
        assert self._has_river(2, 3)  # drawn by hand
        assert self._has_river(7, 3)  # untouched

    def test_painting_water_over_a_river_ends_it_there(self) -> None:
        self._upload()
        paint_terrain(region=self.region, pips=[(57, 32)], terrain="water")
        assert not self._has_river(7, 2)

    def test_reset_puts_back_the_files_rivers_over_staff_paint_and_strokes(self) -> None:
        self._upload()
        paint_terrain(region=self.region, pips=[(57, 33)], terrain="marsh")
        paint_river(region=self.region, pips=[(57, 33)], river=False)
        paint_river(region=self.region, pips=[(52, 33)], river=True)
        count = self._reset()
        assert self._has_river(7, 3)  # a staff-painted pip gets its river back
        assert not self._has_river(2, 3)  # a hand-drawn river goes
        assert TerrainPip.objects.get(x=57, y=33).terrain == Terrain.MARSH
        assert count == TerrainPip.objects.filter(region=self.region, has_river=True).count()
        # the long river stops three pips short of the sea and is carried on to it
        assert self._has_river(8, 19)
        assert self._has_river(9, 19)

    def test_reset_without_a_map_file_is_refused(self) -> None:
        with self.assertRaises(WorldMapServiceError):
            reset_rivers(region=self.region)

    def _seat_a_kingdom_at(self, x: int, y: int) -> None:
        from world.character_creation.factories import RealmFactory
        from world.societies.houses.almanach import plant_rung, rung_area_for_title
        from world.societies.houses.constants import TitleTier
        from world.societies.houses.models import Title

        crown = plant_rung(
            realm=RealmFactory(name="Riverrealm"), tier=TitleTier.KINGDOM, name="Crown"
        )
        capital = Title.objects.get(seat_domain=crown.seat_domain, tier=TitleTier.BARONY)
        set_footprint(area=rung_area_for_title(capital), add=[(50 + x, 30 + y)])

    def test_reset_keeps_the_river_beside_an_inland_kingdom_capital_down_to_its_mouth(self) -> None:
        """The capital is two pips from a stream that joins the short river. Neither
        is a major river; both are kept, the short one only below where they meet."""
        self._upload()
        self._seat_a_kingdom_at(4, 14)
        assert not self._has_river(3, 12)
        self._reset()
        assert self._has_river(4, 12)  # the stream, whole
        assert self._has_river(1, 12)  # where it meets the short river
        assert self._has_river(1, 19)  # the short river's mouth
        assert not self._has_river(1, 11)  # the short river above the meeting

    def test_reset_adds_no_river_for_a_capital_on_the_water(self) -> None:
        self._upload()
        self._seat_a_kingdom_at(4, 10)  # touches the lake's corner at (5, 9)
        self._reset()
        assert not self._has_river(4, 12)
        assert not self._has_river(1, 15)


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

    def test_a_countys_seat_is_its_titles_capital_not_the_first_barony_found(self) -> None:
        """#5157: the map marks a capital, so the seat is the barony the county's title
        is seated in even when another barony of the county lies north of it."""
        from world.character_creation.factories import RealmFactory
        from world.societies.houses.almanach import plant_rung, rung_area_for_title
        from world.societies.houses.constants import TitleTier
        from world.societies.houses.models import Title

        realm = RealmFactory(name="Seatland")
        crown = plant_rung(realm=realm, tier=TitleTier.KINGDOM, name="Seat Crown")
        county = plant_rung(realm=realm, tier=TitleTier.COUNTY, name="Shire", parent_title=crown)
        capital = Title.objects.get(seat_domain=county.seat_domain, tier=TitleTier.BARONY)
        north = plant_rung(realm=realm, tier=TitleTier.BARONY, name="North", parent_title=county)
        set_footprint(area=rung_area_for_title(county), add=[(1, 1), (2, 2)])
        set_footprint(area=rung_area_for_title(north), add=[(1, 1)])
        set_footprint(area=rung_area_for_title(capital), add=[(2, 2)])
        read = region_read(self.region)
        seats = {f.name: f.seat for f in read.footprints}
        assert seats["Shire"] == (2, 2)
        # the crown's own capital holds no pip yet, so it falls back to the first barony
        assert seats["Seat Crown"] == (1, 1)
        assert seats["North"] == (1, 1)

    def test_region_read_carries_charters_and_landless_titles(self) -> None:
        from world.character_creation.factories import RealmFactory
        from world.societies.houses.almanach import (
            charter_fief,
            plant_rung,
            rung_area_for_title,
        )
        from world.societies.houses.constants import TitleStation, TitleTier

        realm = RealmFactory(name="Luxen")
        crown = plant_rung(realm=realm, tier=TitleTier.KINGDOM, name="Republic of Luxen")
        brittany = plant_rung(
            realm=realm, tier=TitleTier.DUCHY, name="Brittany", parent_title=crown
        )
        old_crown = plant_rung(
            realm=realm,
            tier=TitleTier.KINGDOM,
            name="Kingdom of Luxen",
            station=TitleStation.TITULAR,
        )
        empire = plant_rung(
            realm=realm,
            tier=TitleTier.EMPIRE,
            name="The Chimeric Empire",
            station=TitleStation.TITULAR,
        )
        charter_fief(title=old_crown, fief=brittany)
        charter_fief(title=empire, fief=brittany)
        set_footprint(area=rung_area_for_title(brittany), add=[(1, 1), (2, 1)])
        # A duchy has no Domain (#5069): the map names its holder off the title.
        from world.societies.factories import OrganizationFactory
        from world.societies.houses.almanach import assign_holder

        duke = OrganizationFactory(name="House Brittany")
        assign_holder(brittany, duke)
        read = region_read(self.region)
        duchy = next(f for f in read.footprints if f.name == "Brittany")
        assert duchy.holder_org_id == duke.pk
        assert duchy.holder_name == "House Brittany"
        assert sorted(duchy.charters) == sorted([old_crown.pk, empire.pk])
        landless = {t.title_id: t for t in read.landless_titles}
        assert landless[old_crown.pk].name == "Kingdom of Luxen"
        assert landless[old_crown.pk].station == TitleStation.TITULAR
        assert landless[old_crown.pk].fief_ids == [brittany.pk]
        assert landless[old_crown.pk].realm_id == realm.pk
        assert empire.pk in landless
        assert crown.pk not in landless  # it has land through Brittany
        # Brittany's own county and barony are chain members of a landed title, not rungs
        # with no land; a seated crown with no pips yet is listed so it can be carved.
        fresh = plant_rung(realm=realm, tier=TitleTier.KINGDOM, name="New Crown")
        read = region_read(self.region)
        assert {t.title_id for t in read.landless_titles} == {old_crown.pk, empire.pk, fresh.pk}

    def test_pips_endpoint_carries_charters_and_landless_titles(self) -> None:
        """The HTTP payload, not only the service read: the view builds the footprint
        dicts by hand, and the live pass found it dropped `charters` (#4984)."""
        from world.character_creation.factories import RealmFactory
        from world.societies.houses.almanach import charter_fief, plant_rung, rung_area_for_title
        from world.societies.houses.constants import TitleStation, TitleTier

        realm = RealmFactory(name="Wire Realm")
        crown = plant_rung(realm=realm, tier=TitleTier.KINGDOM, name="Wire Crown")
        duchy = plant_rung(realm=realm, tier=TitleTier.DUCHY, name="Wire Duchy", parent_title=crown)
        old_crown = plant_rung(
            realm=realm, tier=TitleTier.KINGDOM, name="Old Wire", station=TitleStation.TITULAR
        )
        charter_fief(title=old_crown, fief=duchy)
        set_footprint(area=rung_area_for_title(duchy), add=[(1, 1)])
        client = APIClient()
        client.force_authenticate(user=AccountFactory(username="wirestaff", is_staff=True))
        response = client.get(f"/api/world-builder/region-maps/{self.region.pk}/pips/")
        assert response.status_code == 200, response.content
        footprints = {f["name"]: f for f in response.data["footprints"]}
        assert footprints["Wire Duchy"]["charters"] == [old_crown.pk]
        landless = {t["title_id"]: t for t in response.data["landless_titles"]}
        assert landless[old_crown.pk]["station"] == TitleStation.TITULAR
        assert landless[old_crown.pk]["fief_ids"] == [duchy.pk]

    def test_adjust_takes_from_anywhere_in_the_kingdom_but_not_a_barony_or_another_kingdom(
        self,
    ) -> None:
        """#4988, #5157: Adjust moves a sibling's pips and a cousin county's in another
        duchy sideways in one stroke; a barony's seat and another kingdom's land stay
        skipped and named."""
        duchy = AreaFactory(name="Duchy", level=AreaLevel.DUCHY, parent=self.kingdom)
        a = AreaFactory(name="Aldmere", level=AreaLevel.COUNTY, parent=duchy)
        b = AreaFactory(name="Brackmere", level=AreaLevel.COUNTY, parent=duchy)
        seat = AreaFactory(name="Seat", level=AreaLevel.BARONY, parent=b)
        other_duchy = AreaFactory(name="Other Duchy", level=AreaLevel.DUCHY, parent=self.kingdom)
        cousin = AreaFactory(name="Cousin", level=AreaLevel.COUNTY, parent=other_duchy)
        cousin_seat = AreaFactory(name="Cousin Seat", level=AreaLevel.BARONY, parent=cousin)
        abroad = AreaFactory(name="Abroad", level=AreaLevel.KINGDOM)
        foreign = AreaFactory(name="Foreign", level=AreaLevel.COUNTY, parent=abroad)
        set_footprint(area=b, add=[(2, 2), (2, 3), (3, 3)])
        set_footprint(area=seat, add=[(3, 3)])
        set_footprint(area=cousin, add=[(8, 8), (8, 7)])
        set_footprint(area=cousin_seat, add=[(8, 7)])
        set_footprint(area=foreign, add=[(6, 6)])
        stroke = [(2, 2), (2, 3), (3, 3), (8, 8), (8, 7), (6, 6)]
        plain = set_footprint(area=a, add=stroke)
        assert plain.added == 0
        assert plain.skipped == 6
        adjusted = set_footprint(area=a, add=stroke, take_from_siblings=True)
        assert adjusted.added == 3
        assert adjusted.skipped == 3
        assert adjusted.skipped_holders == ("Cousin Seat", "Foreign", "Seat")
        assert sorted(adjusted.changed) == [
            (2, 2, b.pk, a.pk),
            (2, 3, b.pk, a.pk),
            (8, 8, cousin.pk, a.pk),
        ]
        assert footprint_of(a) == {(2, 2), (2, 3), (8, 8)}
        assert footprint_of(b) == {(3, 3)}  # the seat barony's pip, still inside Brackmere
        # the duchy lines moved with the county: nothing was written for either duchy
        assert footprint_of(duchy) == {(2, 2), (2, 3), (3, 3), (8, 8)}
        assert footprint_of(other_duchy) == {(8, 7)}
        assert holder_at(6, 6) == foreign

    def test_adjust_on_a_kingdom_takes_only_from_beneath_its_own_parent(self) -> None:
        """#5157: a kingdom has no kingdom above it, so its Adjust keeps the ladder-parent
        scope: a sibling kingdom's land under the same empire, never land outside it."""
        empire = AreaFactory(name="Empire", level=AreaLevel.EMPIRE)
        north = AreaFactory(name="North", level=AreaLevel.KINGDOM, parent=empire)
        south = AreaFactory(name="South", level=AreaLevel.KINGDOM, parent=empire)
        set_footprint(area=south, add=[(4, 4)])
        set_footprint(area=self.county, add=[(5, 5)])  # under a kingdom outside the empire
        adjusted = set_footprint(area=north, add=[(4, 4), (5, 5)], take_from_siblings=True)
        assert adjusted.added == 1
        assert adjusted.skipped_holders == ("County",)
        assert holder_at(4, 4) == north
        assert holder_at(5, 5) == self.county

    def test_move_seat_moves_the_baronys_pip_inside_its_county_and_refuses_outside(
        self,
    ) -> None:
        """#4988: a seat drag moves the barony's single pip to a pip its county holds."""
        from world.areas.worldmap.services import move_seat

        duchy = AreaFactory(name="Duchy", level=AreaLevel.DUCHY, parent=self.kingdom)
        county = AreaFactory(name="Aldmere", level=AreaLevel.COUNTY, parent=duchy)
        seat = AreaFactory(name="Seat", level=AreaLevel.BARONY, parent=county)
        other = AreaFactory(name="Other Seat", level=AreaLevel.BARONY, parent=county)
        cousin = AreaFactory(name="Cousin", level=AreaLevel.COUNTY, parent=duchy)
        set_footprint(area=county, add=[(2, 2), (2, 3), (2, 4), (3, 3)])
        set_footprint(area=seat, add=[(2, 2)])
        set_footprint(area=other, add=[(3, 3)])
        set_footprint(area=cousin, add=[(8, 8)])
        change = move_seat(area=seat, pip=(2, 4))
        assert footprint_of(seat) == {(2, 4)}
        assert sorted(change.changed) == [(2, 2, seat.pk, county.pk), (2, 4, county.pk, seat.pk)]
        assert footprint_of(county) == {(2, 2), (2, 3), (2, 4), (3, 3)}
        for bad in ((3, 3), (8, 8), (9, 9), (2, 4)):
            with self.assertRaises(WorldMapServiceError, msg=str(bad)):
                move_seat(area=seat, pip=bad)
        with self.assertRaises(WorldMapServiceError):
            move_seat(area=county, pip=(2, 3))
        assert footprint_of(seat) == {(2, 4)}

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

    def test_clear_takes_a_domains_own_pips_off_everywhere_and_keeps_its_children(self) -> None:
        set_footprint(area=self.county, add=[(1, 1), (2, 1), (30, 30)])  # (30, 30) is off this map
        set_footprint(area=self.barony, add=[(2, 1)])
        change = clear_footprint(area=self.county)
        assert change.removed == 2
        assert sorted(change.changed) == [
            (1, 1, self.county.pk, self.kingdom.pk),
            (30, 30, self.county.pk, self.kingdom.pk),
        ]
        assert holder_at(2, 1) == self.barony
        assert holder_at(1, 1) == self.kingdom
        change = clear_footprint(area=self.kingdom)
        assert holder_at(1, 1) is None
        assert change.changed == ((1, 1, self.kingdom.pk, None), (30, 30, self.kingdom.pk, None))
        with self.assertRaises(WorldMapServiceError):
            clear_footprint(
                area=AreaFactory(name="Ward2", level=AreaLevel.WARD, parent=self.barony)
            )

    def test_restore_puts_pips_back_with_their_prior_holders(self) -> None:
        duchy = AreaFactory(name="Duchy", level=AreaLevel.DUCHY, parent=self.kingdom)
        county = AreaFactory(name="County2", level=AreaLevel.COUNTY, parent=duchy)
        set_footprint(area=self.kingdom, add=[(6, 6), (7, 6)])
        change = set_footprint(area=county, add=[(6, 6), (7, 6), (8, 6)])
        # an inverse carve would hand (6, 6) to the duchy; a restore hands it to the kingdom
        before = [(x, y, prior) for x, y, prior, _after in change.changed]
        assert restore_pips(pips=before) == 3
        assert holder_at(6, 6) == self.kingdom
        assert holder_at(8, 6) is None
        after = [(x, y, new) for x, y, _prior, new in change.changed]
        assert restore_pips(pips=after) == 3
        assert holder_at(8, 6) == county
        assert AreaFootprintPip.objects.filter(x=6, y=6).count() == 1
        assert restore_pips(pips=[(6, 6, self.kingdom.pk), (6, 6, self.kingdom.pk)]) == 1
        assert holder_at(6, 6) == self.kingdom
        with self.assertRaises(WorldMapServiceError):
            restore_pips(pips=[(6, 6, AreaFactory(name="W3", level=AreaLevel.WARD).pk)])
        with self.assertRaises(WorldMapServiceError):
            restore_pips(pips=[(6, 6, 999999)])

    def test_restore_refuses_more_pips_than_one_call_takes(self) -> None:
        too_many = [(x % 300, x // 300, None) for x in range(MAX_FOOTPRINT_PIPS_PER_CALL + 1)]
        with self.assertRaises(WorldMapServiceError):
            restore_pips(pips=too_many)
        assert restore_pips(pips=too_many[:MAX_FOOTPRINT_PIPS_PER_CALL]) == 0

    def test_rows_at_fetches_only_the_pips_asked_for(self) -> None:
        # (1, 1) and (2, 2) are asked for; (1, 2) and (2, 1) share their x and y sets
        set_footprint(area=self.kingdom, add=[(1, 1), (2, 2), (1, 2), (2, 1)])
        with self.assertNumQueries(1):
            rows = _rows_at({(1, 1), (2, 2), (9, 9)})
        assert set(rows) == {(1, 1), (2, 2)}
        assert list(rows) == [(1, 1), (2, 2)]


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
