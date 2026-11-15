"""Read the modifier value table, level baselines and tapers (#4551, #4594, #5093).

Pure readers over ``ModifierValue``, ``ModifierLevelBaseline`` and ``ModifierTaper``.
Each loads a lane's rows in one query, so a caller valuing many modifiers loads once
and looks up in memory. Value rows read as steps: a level takes the row at the highest
authored level at or below it.

The baselines are the check ladder and the unit of every bonus (#5093): rank N starts at
the level-N baseline total, and ``level_width`` is one level's worth of points. The
baseline rows are dense (one per level); a level above the top row reuses the top row.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from decimal import Decimal

from world.checks.constants import ModifierLane
from world.checks.exceptions import ModifierConfigError
from world.checks.modifier_models import ModifierLevelBaseline, ModifierTaper, ModifierValue
from world.checks.types import TaperRule
from world.traits.models import CheckRank


def _step_lookup(rows: list[tuple[int, int]], level: int) -> int | None:
    """The value at the highest authored level at or below ``level``; rows sorted."""
    levels = [row_level for row_level, _ in rows]
    index = bisect_right(levels, level)
    if index == 0:
        return None
    return rows[index - 1][1]


@dataclass(frozen=True)
class ValueTable:
    """One lane's value table, loaded once: ``value(level, size)`` reads it in memory."""

    rows_by_size: dict[int, list[tuple[int, int]]] = field(default_factory=dict)

    def value(self, level: int, size: int) -> int | None:
        """The modifier's magnitude, or None when no row covers this size and level."""
        rows = self.rows_by_size.get(size)
        if not rows:
            return None
        return _step_lookup(rows, level)

    def signed_value(self, authored_value: int, level: int | None, size: int | None) -> int | None:
        """The table's number for a sized modifier, signed like its authored row, or None.

        The magnitude comes from the row at ``level`` and ``size``; the authored value's
        sign says bonus or penalty, so a debuff or a heavy-armour penalty stays a penalty.
        None (keep the flat authored value) when the source has no level or no size, its
        authored value is 0, or no row covers the pair. Shared by every sized source on a
        lane: technique buffs (#4594) and worn items (#4628).
        """
        if level is None or size is None or authored_value == 0:
            return None
        magnitude = self.value(level, size)
        if magnitude is None:
            return None
        return magnitude if authored_value > 0 else -magnitude


def load_value_table(lane: str = ModifierLane.CHECK) -> ValueTable:
    """Load ``lane``'s ``ModifierValue`` rows in one query."""
    rows_by_size: dict[int, list[tuple[int, int]]] = {}
    for size, level, value in (
        ModifierValue.objects.filter(lane=lane)
        .order_by("size", "level")
        .values_list("size", "level", "value")
    ):
        rows_by_size.setdefault(size, []).append((level, value))
    return ValueTable(rows_by_size=rows_by_size)


def load_taper_rules(lane: str = ModifierLane.CHECK) -> dict[str, TaperRule]:
    """``lane``'s taper rules by source kind, in one query. Empty means no taper."""
    return {
        kind: TaperRule(ratio=ratio, floor=floor)
        for kind, ratio, floor in ModifierTaper.objects.filter(lane=lane).values_list(
            "source_kind", "ratio", "floor"
        )
    }


@dataclass(frozen=True)
class BaselineTable:
    """One lane's level baselines, loaded once: ``baseline`` and ``width`` read it in memory."""

    lane: str = ModifierLane.CHECK
    levels: tuple[int, ...] = ()
    baselines: tuple[int, ...] = ()

    def _index(self, level: int) -> int:
        """The position of the row at ``level``, or of the highest row below it."""
        index = bisect_right(self.levels, level) - 1
        if index < 0:
            msg = f"No {self.lane} level baseline at or below level {level}."
            raise ModifierConfigError(msg)
        return index

    def baseline(self, level: int) -> int:
        """The typical total at ``level``: its row, else the highest row below it.

        Raises ``ModifierConfigError`` when no row sits at or below ``level``.
        """
        return self.baselines[self._index(level)]

    def width(self, level: int) -> int:
        """One level's width at ``level``: the next level's baseline minus this one's.

        At or above the top authored level, the top row's width: its baseline minus the
        row below it. Raises ``ModifierConfigError`` when no row sits at or below
        ``level``, or when the lane has a single row and so no width to read.
        """
        index = self._index(level)
        if index + 1 < len(self.levels):
            return self.baseline(level + 1) - self.baselines[index]
        if index == 0:
            msg = f"The {self.lane} lane needs two level baseline rows to have a level width."
            raise ModifierConfigError(msg)
        return self.baselines[index] - self.baselines[index - 1]


def load_baselines(lane: str = ModifierLane.CHECK) -> BaselineTable:
    """Load ``lane``'s ``ModifierLevelBaseline`` rows in one query."""
    rows = list(
        ModifierLevelBaseline.objects.filter(lane=lane)
        .order_by("level")
        .values_list("level", "baseline")
    )
    return BaselineTable(
        lane=lane,
        levels=tuple(level for level, _ in rows),
        baselines=tuple(baseline for _, baseline in rows),
    )


def level_baseline(level: int, lane: str = ModifierLane.CHECK) -> int:
    """The typical total at ``level`` in ``lane`` (see ``BaselineTable.baseline``)."""
    return load_baselines(lane).baseline(level)


def level_width(level: int, lane: str = ModifierLane.CHECK) -> int:
    """One level's width at ``level`` in ``lane`` (see ``BaselineTable.width``)."""
    return load_baselines(lane).width(level)


def rank_band_share(points: int, at_total: int) -> Decimal | None:
    """How much of one level's width ``points`` spans, for a character at ``at_total``.

    The check lane's step is one level's width at the character's rank (#5093), so staff
    read a check modifier as a share of that width: 0.5 is half a rank for a character at
    ``at_total``. None when ``at_total`` has no rank on the ladder or the lane has no
    width to measure against.
    """
    current = CheckRank.get_rank_for_points(at_total)
    if current is None:
        return None
    try:
        width = level_width(current.rank)
    except ModifierConfigError:
        return None
    if width <= 0:
        return None
    return (Decimal(points) / Decimal(width)).quantize(Decimal("0.01"))
