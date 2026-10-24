"""Read the modifier value table, level baselines and tapers (#4551, #4594).

Pure readers over ``ModifierValue``, ``ModifierLevelBaseline`` and ``ModifierTaper``.
Each loads a lane's rows in one query, so a caller valuing many modifiers loads once
and looks up in memory. Sparse rows read as steps: a level takes the row at the
highest authored level at or below it.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from decimal import Decimal

from world.checks.constants import ModifierLane
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


def level_baseline(level: int, lane: str = ModifierLane.CHECK) -> int | None:
    """The typical total at ``level`` in ``lane``, or None when no row covers it."""
    rows = list(
        ModifierLevelBaseline.objects.filter(lane=lane)
        .order_by("level")
        .values_list("level", "baseline")
    )
    return _step_lookup(rows, level)


def rank_band_share(points: int, at_total: int) -> Decimal | None:
    """How much of the rank band ``at_total`` sits in that ``points`` spans.

    The check lane's step is one rank band at the character's total (#4551 section
    5.5), so staff read a check modifier as a share of that band: 0.5 is half a rank
    for a character at ``at_total``. None when the ladder has no band above
    ``at_total`` to measure against.
    """
    current = CheckRank.get_rank_for_points(at_total)
    if current is None:
        return None
    upper = CheckRank.objects.filter(rank__gt=current.rank).order_by("rank").first()
    if upper is None:
        return None
    width = upper.min_points - current.min_points
    if width <= 0:
        return None
    return (Decimal(points) / Decimal(width)).quantize(Decimal("0.01"))
