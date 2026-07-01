"""ASCII building map (#670) — the telnet face of the room-builder layout.

Pure rendering over ``RoomProfile`` grid coordinates + Exit rows; no writes.
The web map canvas (PR2) reads the same data through the API. Coordinates are
cosmetic: unplaced rooms (NULL grid) list under the grid rather than blocking.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from evennia_extensions.models import RoomProfile

if TYPE_CHECKING:
    from world.buildings.models import Building

CELL_W = 14  # canvas columns per grid cell
CELL_H = 2  # canvas rows per grid cell (room row + connector row)
NAME_W = 10  # max room-name characters inside a box


def _room_label(profile: RoomProfile) -> str:
    name = profile.objectdb.db_key or "?"
    if len(name) > NAME_W:
        name = name[: NAME_W - 1] + "…"
    return f"[{name.center(NAME_W)}]"


def _exit_pairs(room_ids: set[int]) -> set[tuple[int, int]]:
    """Canonical (low, high) id pairs for exits between the given rooms."""
    from evennia.objects.models import ObjectDB  # noqa: PLC0415

    rows = ObjectDB.objects.filter(
        db_typeclass_path="typeclasses.exits.Exit",
        db_location_id__in=list(room_ids),
        db_destination_id__in=list(room_ids),
    ).values_list("db_location_id", "db_destination_id")
    return {(min(a, b), max(a, b)) for a, b in rows}


class _Canvas:
    """A character grid the renderer draws room boxes + connectors onto."""

    def __init__(self, placed: list[RoomProfile]) -> None:
        self.min_x = min(p.grid_x for p in placed)
        self.max_y = max(p.grid_y for p in placed)
        cols = max(p.grid_x for p in placed) - self.min_x + 1
        rows = self.max_y - min(p.grid_y for p in placed) + 1
        self.cells = [[" "] * (cols * CELL_W) for _ in range(rows * CELL_H)]

    def origin(self, p: RoomProfile) -> tuple[int, int]:
        # +y is north → render northmost on top.
        return ((self.max_y - p.grid_y) * CELL_H, (p.grid_x - self.min_x) * CELL_W)

    def put(self, row: int, col: int, text: str) -> None:
        for i, ch in enumerate(text):
            if 0 <= row < len(self.cells) and 0 <= col + i < len(self.cells[0]):
                self.cells[row][col + i] = ch

    def lines(self) -> list[str]:
        return ["".join(r).rstrip() for r in self.cells]


def _draw_connector(canvas: _Canvas, a: RoomProfile, b: RoomProfile) -> bool:
    """Draw the connector for an adjacent pair; False when the pair is non-adjacent."""
    dx, dy = b.grid_x - a.grid_x, b.grid_y - a.grid_y
    if (dx, dy) in {(-1, 0), (1, 0)}:
        left = a if dx == 1 else b
        row, col = canvas.origin(left)
        canvas.put(row, col + NAME_W + 2, "─" * (CELL_W - NAME_W - 2))
    elif (dx, dy) in {(0, -1), (0, 1)}:
        southern = a if dy == 1 else b
        row, col = canvas.origin(southern)
        canvas.put(row - 1, col + NAME_W // 2 + 1, "│")
    elif (dx, dy) in {(1, 1), (-1, -1)}:  # ╱ from south-west to north-east
        south_west = a if (dx, dy) == (1, 1) else b
        row, col = canvas.origin(south_west)
        canvas.put(row - 1, col + NAME_W + 1, "╱")
    elif (dx, dy) in {(1, -1), (-1, 1)}:  # ╲ from north-west to south-east
        north_west = a if (dx, dy) == (1, -1) else b
        row, col = canvas.origin(north_west)
        canvas.put(row + 1, col + NAME_W + 1, "╲")
    else:
        return False
    return True


def _render_grid(placed: list[RoomProfile]) -> list[str]:
    """The grid block: room boxes, connectors, and any far-link footnote."""
    canvas = _Canvas(placed)
    for p in placed:
        row, col = canvas.origin(p)
        canvas.put(row, col, _room_label(p))

    id_to_profile = {p.objectdb_id: p for p in placed}
    far_links: list[str] = []
    for a_id, b_id in sorted(_exit_pairs(set(id_to_profile))):
        a, b = id_to_profile[a_id], id_to_profile[b_id]
        if not _draw_connector(canvas, a, b):
            far_links.append(f"{a.objectdb.db_key} ↔ {b.objectdb.db_key}")

    lines = canvas.lines()
    while lines and not lines[-1]:
        lines.pop()
    if far_links:
        lines.extend(["", "Far links: " + "; ".join(sorted(far_links))])
    return lines


def render_building_map(building: Building, *, floor: int = 0) -> str:
    """Render one floor of the building as an ASCII grid.

    Header carries the space budget; unplaced rooms and cross-floor/far links
    are listed under the grid.
    """
    from world.buildings.room_services import space_used  # noqa: PLC0415

    profiles = list(
        RoomProfile.objects.filter(area=building.area).select_related("objectdb", "size")
    )
    on_floor = [p for p in profiles if p.floor == floor]
    placed = [p for p in on_floor if p.grid_x is not None and p.grid_y is not None]
    unplaced = [p for p in on_floor if p.grid_x is None or p.grid_y is None]

    header = (
        f"{building.area.name} — floor {floor}   "
        f"Space: {space_used(building)}/{building.space_budget}"
    )
    lines = [header, ""]
    if placed:
        lines.extend(_render_grid(placed))
    elif not unplaced:
        lines.append("(no rooms on this floor)")

    if unplaced:
        names = ", ".join(sorted(p.objectdb.db_key for p in unplaced))
        lines.extend(["", f"Unplaced: {names}"])

    other_floors = sorted({p.floor for p in profiles if p.floor != floor})
    if other_floors:
        lines.append(f"Other floors: {', '.join(str(f) for f in other_floors)}")
    return "\n".join(lines)
