"""Read a Fantasy Map Generator ``.map`` file and rasterize it to pips (#4242).

The generator saves its map as fields joined by line breaks (``prepareMapData``
in its ``src/components/save.ts``; verified against the Catenys file of
2026-10-12): the params line first (``version|licence|date|seed|width|height|
id``), then settings, the SVG, and the grid block, a JSON object beginning
``{"spacing":`` with the jittered grid's ``cellsX``, ``cellsY`` and spacing.
The five fields after the grid block are the grid cells' height (0-100, sea
below 20), precipitation, feature id, distance to the coast and temperature;
the field after those is the feature list (type ``ocean`` or ``lake``). Fields
are found by content, never by position: the SVG carries its own line breaks,
so line numbers mean nothing.

Only the grid arrays are read. The generator's finer "pack" cells carry no
coordinates in the file (it rebuilds them on load), and its states, provinces
and burgs are ignored by ruling. Rivers come from the SVG's river layer, whose
paths are flattened and sampled onto the pips. Moisture follows the
generator's own rule (``biomes-generator.ts``): four plus the mean
precipitation of a cell and its land neighbours, plus two on a river.

Every river counts for moisture, but only a few become river pips (#5189): the
file's river records (a JSON list whose rows carry ``i``, ``length`` and
``parent``) say which rivers are main stems and how long each is. The longest
main stems are the major rivers; the rest are streams the map does not draw. A
river's path in the SVG is its outline, down one bank and back up the other, so
its course is the line midway between the two.

Pure Python, no dependency. Coordinates: pip ``x`` grows east, ``y`` south, the
same way the generator's pixels do.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
import json
import math
import re

from world.areas.worldmap.constants import (
    GENERATOR_HILL_HEIGHT,
    GENERATOR_MOUNTAIN_HEIGHT,
    GENERATOR_SEA_LEVEL,
    MAJOR_RIVER_COUNT,
    PIPS_PER_CELL,
    Terrain,
)

# The generator's biome matrix (``biomes-generator.ts``): rows are moisture bands
# (moisture / 5, capped at 4), columns are 20 minus the temperature in degrees,
# 0 to 25. Ids: 1 hot desert, 2 cold desert, 3 savanna, 4 grassland, 5 tropical
# seasonal forest, 6 temperate deciduous forest, 7 tropical rainforest,
# 8 temperate rainforest, 9 taiga, 10 tundra, 11 glacier, 12 wetland.
_BIOME_MATRIX = (
    (1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 10),
    (3, 3, 3, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 9, 9, 9, 9, 10, 10, 10),
    (5, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 9, 9, 9, 9, 9, 10, 10, 10),
    (5, 6, 6, 6, 6, 6, 6, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 9, 9, 9, 9, 9, 9, 10, 10, 10),
    (7, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 9, 9, 9, 9, 9, 9, 9, 10, 10),
)
_GLACIER_BIOME = 11
_GLACIER_MAX_TEMPERATURE = -5  # colder than this is permafrost whatever the moisture
_MOISTURE_BASELINE = 4
_RIVER_MOISTURE = 2
_MOISTURE_BAND_WIDTH = 5
_MOISTURE_BANDS = 4
_TEMPERATURE_BANDS = 25
_BIOME_TO_TERRAIN = {
    1: Terrain.DESERT,
    2: Terrain.DESERT,
    3: Terrain.PLAIN,
    4: Terrain.PLAIN,
    5: Terrain.FOREST,
    6: Terrain.FOREST,
    7: Terrain.FOREST,
    8: Terrain.FOREST,
    9: Terrain.FOREST,
    10: Terrain.TUNDRA,
    11: Terrain.GLACIER,
    12: Terrain.MARSH,
}

_GRID_PREFIX = '{"spacing":'
_LICENCE_PREFIX = "File can be loaded"
_LAKE_FEATURE_TYPE = "lake"
_MIN_FIELDS_WHEN_CRLF = 8
_PARAMS_MIN = 6
_PARAMS_SEED = 3
_PARAMS_WIDTH = 4
_PARAMS_HEIGHT = 5
_FIELDS_AFTER_GRID = 6
_RIVER_GROUP = re.compile(r'<g id="rivers"[^>]*>(.*?)</g>', re.DOTALL)
_PATH_D = re.compile(r'<path [^>]*?\bd="([^"]+)"')
_RIVER_PATH = re.compile(r'<path [^>]*?\bid="river(\d+)"[^>]*?\bd="([^"]+)"')
_RIVER_RECORDS_PREFIX = "[{"
_RIVER_RECORDS_KEY = '"mouth"'
_RIVER_RECORDS_PEEK = 400
_PATH_TOKENS = re.compile(r"[MLCZmlcz]|-?\d*\.?\d+(?:e-?\d+)?")
_CURVE_STEPS = 8
_NEIGHBOUR_OFFSETS = ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1))


class MapFileError(ValueError):
    """The file is not a generator map we can read; ``user_message`` is shown to staff."""

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


Pip = tuple[int, int]
Point = tuple[float, float]


@dataclass(frozen=True)
class GeneratorRiver:
    """One river of the file: its record's length and parent, and its outline path."""

    river_id: int
    length: float
    parent_id: int
    path: str

    @property
    def is_main_stem(self) -> bool:
        """A river that flows into no other; the generator writes 0 or its own id."""
        return self.parent_id in (0, self.river_id)


@dataclass(frozen=True)
class GeneratorMap:
    """The parts of a ``.map`` file the rasterizer reads."""

    version: str
    seed: str
    width_px: int
    height_px: int
    spacing: float
    cells_x: int
    cells_y: int
    heights: list[int]
    precipitation: list[int]
    feature_ids: list[int]
    temperatures: list[int]
    lake_feature_ids: frozenset[int]
    river_paths: tuple[str, ...]
    rivers: tuple[GeneratorRiver, ...] = ()

    def grid_index(self, px: float, py: float) -> int:
        """The grid cell under a pixel, the generator's own ``findGridCell`` arithmetic."""
        col = min(max(int(px // self.spacing), 0), self.cells_x - 1)
        row = min(max(int(py // self.spacing), 0), self.cells_y - 1)
        return row * self.cells_x + col

    def moisture(self) -> list[int]:
        """Per grid cell, the generator's moisture before any river bonus: the
        baseline plus the mean precipitation of the cell and its land neighbours."""
        out = [0] * len(self.heights)
        for idx, height in enumerate(self.heights):
            if height < GENERATOR_SEA_LEVEL:
                continue
            row, col = divmod(idx, self.cells_x)
            samples = [self.precipitation[idx]]
            samples.extend(self.precipitation[n] for n in self._land_neighbours(row, col))
            out[idx] = _MOISTURE_BASELINE + round(sum(samples) / len(samples))
        return out

    def _land_neighbours(self, row: int, col: int) -> list[int]:
        """Read only in-bounds land neighbours; water contributes no precipitation."""
        neighbours = []
        for dx, dy in _NEIGHBOUR_OFFSETS:
            c, r = col + dx, row + dy
            if 0 <= c < self.cells_x and 0 <= r < self.cells_y:
                n = r * self.cells_x + c
                if self.heights[n] >= GENERATOR_SEA_LEVEL:
                    neighbours.append(n)
        return neighbours


@dataclass(frozen=True)
class RasterPip:
    """One pip of a rasterized map, in the map's own (region-local) coordinates."""

    x: int
    y: int
    terrain: str
    height: int
    has_river: bool


def _split_fields(text: str) -> list[str]:
    fields = text.split("\r\n")
    if len(fields) < _MIN_FIELDS_WHEN_CRLF:
        fields = text.split("\n")
    return fields


def _parse_params(line: str) -> tuple[str, str, int, int]:
    params = line.split("|")
    if len(params) < _PARAMS_MIN or not params[0] or not params[1].startswith(_LICENCE_PREFIX):
        msg = "That is not a Fantasy Map Generator .map file."
        raise MapFileError(msg)
    try:
        width_px = int(float(params[_PARAMS_WIDTH]))
        height_px = int(float(params[_PARAMS_HEIGHT]))
    except ValueError as exc:
        msg = "The map file's size line could not be read."
        raise MapFileError(msg) from exc
    if width_px <= 0 or height_px <= 0:
        msg = "The map file reports no size."
        raise MapFileError(msg)
    return params[0], params[_PARAMS_SEED], width_px, height_px


def _int_list(field: str) -> list[int]:
    if not field:
        return []
    return [int(float(v)) for v in field.split(",")]


def _river_paths(fields: list[str], grid_at: int) -> tuple[str, ...]:
    """The river layer's path data, from the SVG that sits before the grid block."""
    svg = "\n".join(fields[1:grid_at])
    group = _RIVER_GROUP.search(svg)
    if not group:
        return ()
    return tuple(_PATH_D.findall(group.group(1)))


def _rivers(fields: list[str], grid_at: int) -> tuple[GeneratorRiver, ...]:
    """The rivers that have both a record and a path. A file without river records
    (an older generator) yields none, so nothing is drawn from a guess."""
    records = next(
        (
            f
            for f in fields
            if f.startswith(_RIVER_RECORDS_PREFIX) and _RIVER_RECORDS_KEY in f[:_RIVER_RECORDS_PEEK]
        ),
        None,
    )
    if records is None:
        return ()
    try:
        rows = json.loads(records)
    except ValueError:
        return ()
    group = _RIVER_GROUP.search("\n".join(fields[1:grid_at]))
    paths = {int(i): d for i, d in _RIVER_PATH.findall(group.group(1))} if group else {}
    out = []
    for row in rows:
        try:
            river_id = int(row["i"])
            river = GeneratorRiver(
                river_id=river_id,
                length=float(row.get("length") or 0),
                parent_id=int(row.get("parent") or 0),
                path=paths[river_id],
            )
        except (KeyError, TypeError, ValueError):
            continue
        out.append(river)
    return tuple(out)


def parse_map(text: str) -> GeneratorMap:
    """Parse the file's text. Raises ``MapFileError`` for anything that is not a map."""
    fields = _split_fields(text)
    version, seed, width_px, height_px = _parse_params(fields[0])
    grid_at = next((i for i, f in enumerate(fields) if f.startswith(_GRID_PREFIX)), None)
    if grid_at is None or grid_at + _FIELDS_AFTER_GRID >= len(fields):
        msg = "The map file has no grid block; it may be from an unsupported version."
        raise MapFileError(msg)
    try:
        grid = json.loads(fields[grid_at])
        heights = _int_list(fields[grid_at + 1])
        precipitation = _int_list(fields[grid_at + 2])
        feature_ids = _int_list(fields[grid_at + 3])
        temperatures = _int_list(fields[grid_at + 5])
        features = json.loads(fields[grid_at + 6])
        cells_x, cells_y, spacing = int(grid["cellsX"]), int(grid["cellsY"]), float(grid["spacing"])
    except (ValueError, TypeError, KeyError) as exc:
        msg = "The map file's grid block could not be read."
        raise MapFileError(msg) from exc
    expected = cells_x * cells_y
    if not (len(heights) == len(feature_ids) == expected) or spacing <= 0:
        msg = "The map file's grid block is inconsistent."
        raise MapFileError(msg)
    if len(precipitation) != expected:
        precipitation = [0] * expected
    if len(temperatures) != expected:
        temperatures = [10] * expected
    lakes = frozenset(
        int(f["i"]) for f in features if isinstance(f, dict) and f.get("type") == _LAKE_FEATURE_TYPE
    )
    return GeneratorMap(
        version=version,
        seed=seed,
        width_px=width_px,
        height_px=height_px,
        spacing=spacing,
        cells_x=cells_x,
        cells_y=cells_y,
        heights=heights,
        precipitation=precipitation,
        feature_ids=feature_ids,
        temperatures=temperatures,
        lake_feature_ids=lakes,
        river_paths=_river_paths(fields, grid_at),
        rivers=_rivers(fields, grid_at),
    )


def height_cells_for(gmap: GeneratorMap, width_cells: int) -> int:
    """The region's height in cells, from the file's aspect ratio; never zero."""
    return max(1, round(width_cells * gmap.height_px / gmap.width_px))


def biome_id(temperature: int, moisture: int) -> int:
    """The generator's biome from a cell's temperature and moisture."""
    if temperature < _GLACIER_MAX_TEMPERATURE:
        return _GLACIER_BIOME
    moisture_band = min(moisture // _MOISTURE_BAND_WIDTH, _MOISTURE_BANDS)
    temperature_band = min(max(20 - temperature, 0), _TEMPERATURE_BANDS)
    return _BIOME_MATRIX[moisture_band][temperature_band]


def terrain_for(height: int, temperature: int, moisture: int, *, is_lake: bool) -> str:
    """Pip terrain from the generator's numbers."""
    if height < GENERATOR_SEA_LEVEL:
        return Terrain.LAKE if is_lake else Terrain.WATER
    if height >= GENERATOR_MOUNTAIN_HEIGHT:
        return Terrain.MOUNTAIN
    biome = biome_id(temperature, moisture)
    if biome == _GLACIER_BIOME:
        return Terrain.GLACIER
    if height >= GENERATOR_HILL_HEIGHT:
        return Terrain.HILL
    return _BIOME_TO_TERRAIN[biome]


def _cubic(p0: tuple[float, float], p1: tuple[float, float], p2: tuple[float, float],
           p3: tuple[float, float]) -> list[tuple[float, float]]:  # fmt: skip
    out = []
    for s in range(1, _CURVE_STEPS + 1):
        t = s / _CURVE_STEPS
        u = 1 - t
        a, b, c, d = u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t
        out.append(
            (
                a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
                a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1],
            )
        )
    return out


def flatten_path(d: str) -> list[tuple[float, float]]:
    """The points along an SVG path of absolute M, L, C and Z commands (the river
    layer uses M and C). Curves become straight pieces."""
    tokens = _PATH_TOKENS.findall(d)
    points: list[tuple[float, float]] = []
    command = "M"
    start: tuple[float, float] | None = None
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.isalpha():
            command = tok.upper()
            i += 1
            if command == "Z" and start is not None:
                points.append(start)
            continue
        segment, consumed = _path_segment(command, tokens, i, points)
        if not consumed:
            break
        points.extend(segment)
        if command == "M":
            start = segment[-1]
            command = "L"
        i += consumed
    return points


def river_pips(gmap: GeneratorMap, scale: float, width: int, height: int) -> set[tuple[int, int]]:
    """The pips any river path crosses; paths are sampled every half pip. This is
    every river and stream, and feeds moisture only (#5189)."""
    step = scale / 2
    hit: set[tuple[int, int]] = set()
    for d in gmap.river_paths:
        for (ax, ay), (bx, by) in pairwise(flatten_path(d)):
            n = max(1, int(math.hypot(bx - ax, by - ay) / step))
            for k in range(n + 1):
                t = k / n
                x, y = int((ax + (bx - ax) * t) // scale), int((ay + (by - ay) * t) // scale)
                if 0 <= x < width and 0 <= y < height:
                    hit.add((x, y))
    return hit


def major_rivers(gmap: GeneratorMap) -> tuple[GeneratorRiver, ...]:
    """The longest main stems, the only rivers an upload draws (#5189)."""
    stems = sorted(
        (r for r in gmap.rivers if r.is_main_stem), key=lambda r: (-r.length, r.river_id)
    )
    return tuple(stems[:MAJOR_RIVER_COUNT])


def river_course(river: GeneratorRiver) -> list[Point]:
    """The river's middle line from source to mouth: the point midway between
    each bank point and its opposite number on the way back. The generator draws
    the outline from the mouth up one bank and back down the other (checked
    against the Catenys file: the first point of each long river is at the sea),
    so the middle line is turned round."""
    outline = flatten_path(river.path)
    last = len(outline) - 1
    upstream = [
        ((outline[k][0] + outline[last - k][0]) / 2, (outline[k][1] + outline[last - k][1]) / 2)
        for k in range((len(outline) + 1) // 2)
    ]
    return upstream[::-1]


def _touching(a: Pip, b: Pip) -> bool:
    return abs(a[0] - b[0]) <= 1 and abs(a[1] - b[1]) <= 1


def _thin(chain: list[Pip]) -> list[Pip]:
    """A chain one pip wide: a pip visited twice cuts out the loop between the
    visits, and a pip whose two neighbours in the chain already touch is dropped."""
    walked: list[Pip] = []
    for pip in chain:
        if pip in walked:
            del walked[walked.index(pip) + 1 :]
            continue
        walked.append(pip)
    out: list[Pip] = []
    for pip in walked:
        while len(out) > 1 and _touching(out[-2], pip):
            out.pop()
        out.append(pip)
    return out


def river_chain(river: GeneratorRiver, scale: float, width: int, height: int) -> list[Pip]:
    """The pips the river's course crosses, in order from source to mouth, one
    pip wide. The course is sampled every half pip."""
    step = scale / 2
    chain: list[Pip] = []
    for (ax, ay), (bx, by) in pairwise(river_course(river)):
        n = max(1, int(math.hypot(bx - ax, by - ay) / step))
        for k in range(n + 1):
            t = k / n
            pip = (int((ax + (bx - ax) * t) // scale), int((ay + (by - ay) * t) // scale))
            if 0 <= pip[0] < width and 0 <= pip[1] < height and (not chain or chain[-1] != pip):
                chain.append(pip)
    return _thin(chain)


def major_river_chains(
    gmap: GeneratorMap, scale: float, width: int, height: int
) -> list[list[Pip]]:
    """Each major river's course as pips, source to mouth."""
    return [river_chain(river, scale, width, height) for river in major_rivers(gmap)]


def _gap(pip: Pip, chain: list[Pip]) -> int:
    """How many pips from ``pip`` to the nearest pip of ``chain``, diagonals as one."""
    return min(max(abs(pip[0] - x), abs(pip[1] - y)) for x, y in chain)


def capital_river_chains(  # noqa: PLR0913 - a raster's geometry plus the capitals
    gmap: GeneratorMap,
    scale: float,
    width: int,
    height: int,
    capitals: list[Pip],
    reach: int,
) -> list[list[Pip]]:
    """For each capital, one course from source to mouth: the river nearest it
    within ``reach`` pips, whole, then each river that one flows into from where
    they meet down to the mouth (#5189). A capital with no river that near adds
    nothing."""
    chains = {r.river_id: river_chain(r, scale, width, height) for r in gmap.rivers}
    by_id = {r.river_id: r for r in gmap.rivers}
    courses: list[list[Pip]] = []
    for capital in capitals:
        near = [
            (_gap(capital, chain), -by_id[river_id].length, river_id)
            for river_id, chain in chains.items()
            if chain
        ]
        if not near or min(near)[0] > reach:
            continue
        river = by_id[min(near)[2]]
        course = list(chains[river.river_id])
        seen = {river.river_id}
        while not river.is_main_stem and river.parent_id in by_id:
            mouth = chains[river.river_id][-1]
            river = by_id[river.parent_id]
            if river.river_id in seen or not chains[river.river_id]:
                break
            seen.add(river.river_id)
            downstream = chains[river.river_id]
            meeting = min(
                range(len(downstream)),
                key=lambda i: max(
                    abs(downstream[i][0] - mouth[0]), abs(downstream[i][1] - mouth[1])
                ),
            )
            course.extend(downstream[meeting:])
        courses.append(course)
    return courses


def rasterize(gmap: GeneratorMap, width_cells: int, height_cells: int) -> list[RasterPip]:
    """Every pip of a ``width_cells`` by ``height_cells`` raster of the map. Every
    river wets the ground it crosses; only the major rivers are river pips."""
    width, height = width_cells * PIPS_PER_CELL, height_cells * PIPS_PER_CELL
    scale = gmap.width_px / width
    wet = river_pips(gmap, scale, width, height)
    rivers = {pip for chain in major_river_chains(gmap, scale, width, height) for pip in chain}
    moisture = gmap.moisture()
    out: list[RasterPip] = []
    for y in range(height):
        cy = (y + 0.5) * scale
        for x in range(width):
            idx = gmap.grid_index((x + 0.5) * scale, cy)
            h = gmap.heights[idx]
            land = h >= GENERATOR_SEA_LEVEL
            has_river = (x, y) in rivers and land
            terrain = terrain_for(
                h,
                gmap.temperatures[idx],
                moisture[idx] + (_RIVER_MOISTURE if (x, y) in wet and land else 0),
                is_lake=gmap.feature_ids[idx] in gmap.lake_feature_ids,
            )
            out.append(
                RasterPip(
                    x=x, y=y, terrain=terrain, height=max(0, min(100, h)), has_river=has_river
                )
            )
    return out


def _path_segment(
    command: str, tokens: list[str], offset: int, points: list[tuple[float, float]]
) -> tuple[list[tuple[float, float]], int]:
    """Consume one absolute line or cubic segment, stopping on incomplete coordinates."""
    if command == "C":
        if offset + 5 >= len(tokens) or not points:
            return [], 0
        nums = [float(t) for t in tokens[offset : offset + 6]]
        return list(
            _cubic(points[-1], (nums[0], nums[1]), (nums[2], nums[3]), (nums[4], nums[5]))
        ), 6
    if offset + 1 >= len(tokens):
        return [], 0
    return [(float(tokens[offset]), float(tokens[offset + 1]))], 2
