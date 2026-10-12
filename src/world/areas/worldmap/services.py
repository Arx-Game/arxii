"""World map writes and reads (#4242, ADR-0328).

Every write refuses with a ``WorldMapServiceError`` whose ``user_message`` is
the sentence a staff member sees. The reads build the payload the Atlas's
region-map view draws from. Nothing here routes or travels over pips: a pip
is ground on a map, connectivity stays exits (ADR-0120).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import gzip
from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from world.areas.constants import AreaLevel, GridOrigin
from world.areas.models import Area
from world.areas.worldmap.azgaar import (
    MapFileError,
    height_cells_for,
    parse_map,
    rasterize,
)
from world.areas.worldmap.constants import (
    PIPS_PER_CELL,
    WATER_TERRAINS,
    PipSource,
    Terrain,
)
from world.areas.worldmap.models import (
    AreaFootprintPip,
    RegionMap,
    RegionMapUpload,
    TerrainPip,
)

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.societies.houses.models import Title
    from world.societies.models import Organization

Pip = tuple[int, int]

MAX_MAP_FILE_BYTES = 64 * 1024 * 1024
MAX_WIDTH_CELLS = 100
MAX_PAINT_PIPS = 20000
MAX_FOOTPRINT_PIPS_PER_CALL = 20000


class WorldMapServiceError(Exception):
    """A refused map write; ``user_message`` is safe to show."""

    def __init__(self, message: str, *, user_message: str | None = None) -> None:
        super().__init__(message)
        self.user_message = user_message or message


# --------------------------------------------------------------------------- regions


def create_region_map(  # noqa: PLR0913
    *,
    name: str,
    anchor_x: int,
    anchor_y: int,
    width_cells: int,
    area: Area | None = None,
    new_continent: bool = False,
    actor: AccountDB | None = None,
) -> RegionMap:
    """A new region on the world grid. Refuses a blank name, a silly width, and an
    anchor box that overlaps a region already placed (seams touch, never overlap).

    ``new_continent`` makes the region the geography of a CONTINENT rung by the same
    name: an existing one is linked, otherwise an authored one is created in the same
    transaction (ApostateCD, 2026-10-12: Catenys the map is Catenys the continent).
    """
    name = name.strip()
    if not name:
        msg = "A region needs a name."
        raise WorldMapServiceError(msg)
    if not 1 <= width_cells <= MAX_WIDTH_CELLS:
        msg = f"width_cells {width_cells} out of range"
        raise WorldMapServiceError(
            msg, user_message=f"A region is 1 to {MAX_WIDTH_CELLS} cells wide."
        )
    if RegionMap.objects.filter(name__iexact=name).exists():
        msg = f"region {name!r} exists"
        raise WorldMapServiceError(msg, user_message="A region by that name already exists.")
    for other in RegionMap.objects.all():
        other_h = other.height_cells or 1
        if (
            anchor_x < other.anchor_x + other.width_cells
            and other.anchor_x < anchor_x + width_cells
            and anchor_y < other.anchor_y + other_h
            and other.anchor_y < anchor_y + other_h
        ):
            msg = f"region {name!r} overlaps {other.name!r}"
            raise WorldMapServiceError(
                msg, user_message=f"That anchor and width overlap {other.name}."
            )
    with transaction.atomic():
        if new_continent:
            area = _continent_named(name)
        return RegionMap.objects.create(
            name=name,
            anchor_x=anchor_x,
            anchor_y=anchor_y,
            width_cells=width_cells,
            area=area,
            created_by=actor,
        )


def _continent_named(name: str) -> Area:
    """The CONTINENT rung a region is the geography of: the one already named so,
    else a new authored one (``Area.save`` runs ``full_clean``; a slug another area
    holds is the one way that fails)."""
    existing = Area.objects.filter(level=AreaLevel.CONTINENT, name__iexact=name).first()
    if existing is not None:
        return existing
    continent = Area(
        name=name,
        slug=slugify(name)[:100],
        level=AreaLevel.CONTINENT,
        origin=GridOrigin.AUTHORED,
    )
    try:
        continent.save()
    except ValidationError as exc:
        msg = f"continent {name!r} could not be created: {exc.messages}"
        raise WorldMapServiceError(msg, user_message="; ".join(exc.messages)) from exc
    return continent


# --------------------------------------------------------------------------- uploads


def import_region_map_file(
    *,
    region: RegionMap,
    file_name: str,
    data: bytes,
    actor: AccountDB | None = None,
) -> RegionMapUpload:
    """Keep an uploaded generator file for ``region`` and rasterize it. The file is
    parsed before anything is written, so a bad file writes nothing."""
    if len(data) > MAX_MAP_FILE_BYTES:
        msg = "That file is larger than a map file can be."
        raise WorldMapServiceError(msg)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        msg = "That is not a Fantasy Map Generator .map file."
        raise WorldMapServiceError(msg) from exc
    try:
        gmap = parse_map(text)
    except MapFileError as exc:
        raise WorldMapServiceError(str(exc), user_message=exc.user_message) from exc
    height_cells = height_cells_for(gmap, region.width_cells)
    with transaction.atomic():
        if region.height_cells and region.height_cells != height_cells:
            msg = f"aspect changed: {region.height_cells} -> {height_cells} cells"
            raise WorldMapServiceError(
                msg,
                user_message=(
                    "That file's shape does not match the region's: it would be "
                    f"{height_cells} cells tall, and the region is {region.height_cells}."
                ),
            )
        if not region.height_cells:
            region.height_cells = height_cells
            region.save(update_fields=["height_cells"])
        upload = RegionMapUpload.objects.create(
            region=region,
            file_name=(file_name or "map.map")[:200],
            file_bytes=gzip.compress(data),
            byte_size=len(data),
            generator_version=gmap.version[:40],
            source_width_px=gmap.width_px,
            source_height_px=gmap.height_px,
            uploaded_by=actor,
        )
        _write_generator_pips(region, rasterize(gmap, region.width_cells, height_cells))
        upload.rasterized_at = timezone.now()
        upload.save(update_fields=["rasterized_at"])
    return upload


def rasterize_upload(upload: RegionMapUpload) -> int:
    """Re-run the rasterize step from a kept upload (after a code change to the
    rasterizer, say). Returns the number of generator pips written."""
    region = upload.region
    gmap = parse_map(upload_text(upload))
    with transaction.atomic():
        count = _write_generator_pips(
            region, rasterize(gmap, region.width_cells, region.height_cells)
        )
        upload.rasterized_at = timezone.now()
        upload.save(update_fields=["rasterized_at"])
    return count


def upload_text(upload: RegionMapUpload) -> str:
    """The uploaded file, decompressed."""
    return gzip.decompress(bytes(upload.file_bytes)).decode("utf-8")


def _write_generator_pips(region: RegionMap, raster: Iterable) -> int:
    """Replace the region's generator pips; a staff-painted pip keeps its square."""
    TerrainPip.objects.filter(region=region, source=PipSource.GENERATOR).delete()
    staff = set(
        TerrainPip.objects.filter(region=region, source=PipSource.STAFF).values_list("x", "y")
    )
    x0, y0 = region.pip_x0, region.pip_y0
    rows = [
        TerrainPip(
            region=region,
            x=x0 + p.x,
            y=y0 + p.y,
            terrain=p.terrain,
            height=p.height,
            has_river=p.has_river,
            source=PipSource.GENERATOR,
        )
        for p in raster
        if (x0 + p.x, y0 + p.y) not in staff
    ]
    TerrainPip.objects.bulk_create(rows, batch_size=5000)
    return len(rows)


# --------------------------------------------------------------------------- paint


def paint_terrain(
    *,
    region: RegionMap,
    pips: Iterable[Pip],
    terrain: str,
) -> int:
    """Set ``terrain`` on ``pips`` as a staff edit. Pips outside the region are
    refused; a painted pip survives every later upload. Returns the count."""
    if terrain not in Terrain.values:
        options = ", ".join(Terrain.values)
        msg = f"No '{terrain}' terrain. Options: {options}."
        raise WorldMapServiceError(msg)
    wanted = _unique_pips(pips, MAX_PAINT_PIPS)
    outside = [p for p in wanted if not _inside_region(region, p)]
    if outside:
        msg = "Some of those pips are outside this region."
        raise WorldMapServiceError(msg)
    with transaction.atomic():
        existing = {
            (row.x, row.y): row
            for row in TerrainPip.objects.filter(
                region=region, x__in={p[0] for p in wanted}, y__in={p[1] for p in wanted}
            )
            if (row.x, row.y) in wanted
        }
        for row in existing.values():
            row.terrain = terrain
            row.source = PipSource.STAFF
        TerrainPip.objects.bulk_update_with_reason(
            list(existing.values()),
            ["terrain", "source"],
            batch_size=5000,
            reason="staff paint rewrites rows loaded in this transaction",
        )
        TerrainPip.objects.bulk_create(
            [
                TerrainPip(region=region, x=x, y=y, terrain=terrain, source=PipSource.STAFF)
                for (x, y) in wanted
                if (x, y) not in existing
            ],
            batch_size=5000,
        )
    return len(wanted)


# --------------------------------------------------------------------------- footprints


def _ladder_parent(area: Area) -> Area | None:
    """The nearest ancestor that can hold a footprint (BARONY or above), or None."""
    parent = area.parent
    while parent is not None and parent.level < AreaLevel.BARONY:
        parent = parent.parent
    return parent


def _is_ancestor(candidate: Area, area: Area) -> bool:
    node: Area | None = area.parent
    while node is not None:
        if node.pk == candidate.pk:
            return True
        node = node.parent
    return False


def set_footprint(
    *,
    area: Area,
    add: Iterable[Pip] = (),
    remove: Iterable[Pip] = (),
) -> tuple[int, int]:
    """Grow or shrink an area's footprint. A pip row names its lowest holder, so
    carving a barony inside a county moves the county's row to the barony, and
    shrinking the barony hands the row back to the county. Refuses water, a pip
    another domain holds (one that is not an ancestor of ``area``), and taking
    back a pip a descendant stands on. Returns ``(added, removed)``."""
    to_add = _unique_pips(add, MAX_FOOTPRINT_PIPS_PER_CALL)
    to_remove = _unique_pips(remove, MAX_FOOTPRINT_PIPS_PER_CALL)
    if not to_add and not to_remove:
        return 0, 0
    if area.level < AreaLevel.BARONY:
        msg = "Only a barony or a larger domain has a footprint."
        raise WorldMapServiceError(msg)
    added = removed = 0
    with transaction.atomic():
        if to_add:
            _refuse_water(to_add)
            added = _claim(area, to_add)
        if to_remove:
            removed = _release(area, to_remove)
    return added, removed


def _rows_at(pips: set[Pip]) -> dict[Pip, AreaFootprintPip]:
    rows = AreaFootprintPip.objects.filter(
        x__in={p[0] for p in pips}, y__in={p[1] for p in pips}
    ).select_related("area")
    return {(r.x, r.y): r for r in rows if (r.x, r.y) in pips}


def _claim(area: Area, pips: set[Pip]) -> int:
    """Give ``pips`` to ``area``: open ground is taken; an ancestor's pip moves
    down to this area; a pip held by this area or a descendant is already inside;
    any other holder refuses."""
    held = _rows_at(pips)
    moving: list[AreaFootprintPip] = []
    for pip, row in held.items():
        holder = row.area
        if holder.pk == area.pk or _is_ancestor(area, holder):
            continue  # already inside this footprint
        if _is_ancestor(holder, area):
            row.area = area
            moving.append(row)
            continue
        x, y = pip
        msg = f"Pip ({x}, {y}) is in {holder.name or 'another domain'}'s footprint."
        raise WorldMapServiceError(msg)
    if moving:
        AreaFootprintPip.objects.bulk_update_with_reason(
            moving, ["area"], batch_size=5000, reason="carve moves rows loaded in this transaction"
        )
    fresh = [AreaFootprintPip(area=area, x=x, y=y) for (x, y) in pips if (x, y) not in held]
    AreaFootprintPip.objects.bulk_create(fresh, batch_size=5000)
    return len(fresh) + len(moving)


def _release(area: Area, pips: set[Pip]) -> int:
    """Take ``pips`` out of ``area``: its own rows go to its ladder parent, or to open
    ground when it has none; a descendant's row is refused; anyone else's is left alone."""
    held = _rows_at(pips)
    parent = _ladder_parent(area)
    to_parent: list[AreaFootprintPip] = []
    to_open: list[int] = []
    for pip, row in held.items():
        holder = row.area
        if holder.pk == area.pk:
            if parent is not None:
                row.area = parent
                to_parent.append(row)
            else:
                to_open.append(row.pk)
            continue
        if _is_ancestor(area, holder):
            x, y = pip
            msg = (
                f"Pip ({x}, {y}) is in {holder.name or 'a child domain'}'s footprint; "
                "shrink that first."
            )
            raise WorldMapServiceError(msg)
    if to_parent:
        AreaFootprintPip.objects.bulk_update_with_reason(
            to_parent,
            ["area"],
            batch_size=5000,
            reason="shrink moves rows loaded in this transaction",
        )
    if to_open:
        AreaFootprintPip.objects.filter(pk__in=to_open).delete()
    return len(to_parent) + len(to_open)


def _refuse_water(pips: set[Pip]) -> None:
    rows = TerrainPip.objects.filter(x__in={p[0] for p in pips}, y__in={p[1] for p in pips})
    wet = [(r.x, r.y) for r in rows if (r.x, r.y) in pips and r.terrain in WATER_TERRAINS]
    if wet:
        x, y = wet[0]
        msg = f"Pip ({x}, {y}) is water; a footprint is land."
        raise WorldMapServiceError(msg)


def holder_at(x: int, y: int) -> Area | None:
    """The area whose footprint holds the pip, or None for open ground."""
    row = AreaFootprintPip.objects.filter(x=x, y=y).select_related("area").first()
    return row.area if row is not None else None


def footprint_of(area: Area) -> set[Pip]:
    """Every pip inside an area: its own rows and every descendant's. The descendants
    are walked by ``parent`` a rung at a time (the ladder is a handful deep), so the
    read is the same on the SQLite tier, where the closure view is absent."""
    ids = {area.pk}
    frontier = [area.pk]
    while frontier:
        frontier = list(
            Area.objects.filter(parent_id__in=frontier)
            .exclude(pk__in=ids)
            .values_list("pk", flat=True)
        )
        ids.update(frontier)
    return set(AreaFootprintPip.objects.filter(area_id__in=ids).values_list("x", "y"))


# --------------------------------------------------------------------------- reads


@dataclass(frozen=True)
class FootprintRead:
    area_id: int
    name: str
    level: int
    level_display: str
    parent_id: int | None
    realm_id: int | None
    holder_org_id: int | None
    holder_name: str
    title_id: int | None
    seat: Pip | None
    pips: list[Pip]


@dataclass(frozen=True)
class RegionRead:
    region: RegionMap
    pips: list[tuple[int, int, str, bool]]
    footprints: list[FootprintRead]


def region_read(region: RegionMap) -> RegionRead:
    """Everything the region-map view draws: the terrain pips and every footprint
    that touches the region's box, with its holder and Almanach title."""
    x0, y0 = region.pip_x0, region.pip_y0
    x1, y1 = x0 + region.width_cells * PIPS_PER_CELL, y0 + region.height_cells * PIPS_PER_CELL
    pips = list(
        TerrainPip.objects.filter(region=region).values_list("x", "y", "terrain", "has_river")
    )
    rows = list(
        AreaFootprintPip.objects.filter(x__gte=x0, x__lt=x1, y__gte=y0, y__lt=y1)
        .order_by("y", "x")
        .values_list("area_id", "x", "y")
    )
    holders = {
        a.pk: a
        for a in Area.objects.filter(pk__in={r[0] for r in rows}).select_related(
            "domain_profile__owner_org", "parent"
        )
    }
    # a pip belongs to its holder and to every ancestor of the holder on the ladder
    by_area: dict[int, list[Pip]] = {}
    areas: dict[int, Area] = {}
    for area_id, x, y in rows:
        node: Area | None = holders[area_id]
        while node is not None:
            if node.level >= AreaLevel.BARONY:
                by_area.setdefault(node.pk, []).append((x, y))
                areas[node.pk] = node
            node = node.parent
    titles = _title_by_area(areas.values())
    seats = _seat_by_area(areas, by_area)
    footprints = []
    for area_id, area_pips in by_area.items():
        area = areas[area_id]
        org = _holder_of(area)
        footprints.append(
            FootprintRead(
                area_id=area.pk,
                name=area.name,
                level=area.level,
                level_display=area.get_level_display(),
                parent_id=area.parent_id,
                realm_id=area.realm_id,
                holder_org_id=org.pk if org is not None else None,
                holder_name=org.name if org is not None else "",
                title_id=titles.get(area.pk),
                seat=seats.get(area.pk),
                pips=area_pips,
            )
        )
    footprints.sort(key=lambda f: (f.level, f.name))
    return RegionRead(region=region, pips=pips, footprints=footprints)


def _holder_of(area: Area) -> Organization | None:
    """The house holding an area's domain, or None for an unclaimed or undecorated area."""
    try:
        domain = area.domain_profile
    except ObjectDoesNotExist:
        return None
    return domain.owner_org


def _title_by_area(areas: Iterable[Area]) -> dict[int, int]:
    """The Almanach title standing on each area, by the title's own rung level (the
    walk ``_rung_area`` does, done once for every title with a seat)."""
    from world.societies.houses.constants import TIER_TO_AREA_LEVEL  # noqa: PLC0415
    from world.societies.houses.models import Title  # noqa: PLC0415

    wanted = {a.pk for a in areas}
    if not wanted:
        return {}
    out: dict[int, int] = {}
    titles: Iterable[Title] = Title.objects.filter(seat_domain__isnull=False).select_related(
        "seat_domain__area"
    )
    for title in titles:
        level = TIER_TO_AREA_LEVEL.get(title.tier)
        area: Area | None = title.seat_domain.area
        while area is not None and area.level != level:
            area = area.parent
        if area is not None and area.pk in wanted and area.pk not in out:
            out[area.pk] = title.pk
    return out


def _seat_by_area(areas: dict[int, Area], by_area: dict[int, list[Pip]]) -> dict[int, Pip]:
    """A footprint's seat pip: the first pip of its seat barony's own footprint, for
    every area the barony sits inside. A barony's seat is its own pip."""
    seats: dict[int, Pip] = {}
    for barony_id, pips in by_area.items():
        barony = areas[barony_id]
        if barony.level != AreaLevel.BARONY or not pips:
            continue
        node: Area | None = barony
        while node is not None:
            seats.setdefault(node.pk, pips[0])
            node = node.parent
    return seats


# --------------------------------------------------------------------------- helpers


def _unique_pips(pips: Iterable[Pip], cap: int) -> set[Pip]:
    out: set[Pip] = set()
    for p in pips:
        try:
            x, y = int(p[0]), int(p[1])
        except (TypeError, ValueError, IndexError) as exc:
            msg = "Pips are pairs of whole numbers."
            raise WorldMapServiceError(msg) from exc
        out.add((x, y))
        if len(out) > cap:
            msg = f"At most {cap} pips in one call."
            raise WorldMapServiceError(msg)
    return out


def _inside_region(region: RegionMap, pip: Pip) -> bool:
    x0, y0 = region.pip_x0, region.pip_y0
    return (
        x0 <= pip[0] < x0 + region.width_cells * PIPS_PER_CELL
        and y0 <= pip[1] < y0 + region.height_cells * PIPS_PER_CELL
    )
