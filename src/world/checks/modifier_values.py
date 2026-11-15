"""Read modifier values, level baselines and tapers (#4551, #4594, #5093).

Pure readers over ``ModifierSizeFraction``, ``ModifierValue``, ``ModifierLevelBaseline``
and ``ModifierTaper``. Each loads a lane's rows once, so a caller valuing many modifiers
loads once and looks up in memory.

A modifier's value is derived: its size's fraction times one level's width at the level
it was applied at. A ``ModifierValue`` row at exactly that level and size overrides the
derived number.

The baselines are the check ladder and the unit of every bonus (#5093): rank N starts at
the level-N baseline total, and ``level_width`` is one level's worth of points. The
baseline rows are dense (one per level); a level above the top row reuses the top row.

A ``LevelTier`` row adds a jump of ``bonus_points`` to every level from its start level up
(``tier_bonus``). It is added in full wherever a level's strength is read, and it does not
change ``level_width``.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from decimal import Decimal

from world.checks.constants import ModifierLane
from world.checks.exceptions import ModifierConfigError
from world.checks.modifier_models import (
    LevelTier,
    ModifierLevelBaseline,
    ModifierSizeFraction,
    ModifierTaper,
    ModifierValue,
)
from world.checks.types import TaperRule, round_half_up
from world.traits.models import CheckRank


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


@dataclass(frozen=True)
class TierTable:
    """The level tiers, loaded once: ``bonus(level)`` reads it in memory (#5093).

    ``starts`` holds each tier's start level, lowest first, and ``totals`` the running sum
    of ``bonus_points`` up to and including that tier.
    """

    starts: tuple[int, ...] = ()
    totals: tuple[int, ...] = ()

    def bonus(self, level: int) -> int:
        """The sum of ``bonus_points`` over every tier starting at or below ``level``.

        0 when no tier starts at or below ``level`` (and so on a database with no tiers).
        """
        index = bisect_right(self.starts, level)
        return self.totals[index - 1] if index else 0


@dataclass(frozen=True)
class ValueTable:
    """One lane's modifier values, loaded once: ``value(level, size)`` reads it in memory.

    ``overrides`` maps an exact (level, size) to its authored value; ``fractions`` maps a
    size to its share of one level's width; ``baselines`` supplies the width.
    """

    overrides: dict[tuple[int, int], int] = field(default_factory=dict)
    fractions: dict[int, Decimal] = field(default_factory=dict)
    baselines: BaselineTable = field(default_factory=BaselineTable)

    def value(self, level: int, size: int) -> int | None:
        """The modifier's magnitude at ``level`` and ``size``, or None when none is defined.

        The override row at exactly this level and size wins. Otherwise the size's
        fraction times one level's width at ``level``, rounded half up, never below 1
        while the fraction is nonzero. None when the size has no fraction and no override.
        Raises ``ModifierConfigError`` when a fraction needs a width the lane's baseline
        rows cannot give.
        """
        override = self.overrides.get((level, size))
        if override is not None:
            return override
        fraction = self.fractions.get(size)
        if fraction is None:
            return None
        magnitude = round_half_up(fraction * self.baselines.width(level))
        return max(1, magnitude) if fraction > 0 else magnitude

    def signed_value(self, authored_value: int, level: int | None, size: int | None) -> int | None:
        """The table's number for a sized modifier, signed like its authored row, or None.

        The magnitude comes from ``value`` at ``level`` and ``size``; the authored value's
        sign says bonus or penalty, so a debuff or a heavy-armour penalty stays a penalty,
        and a small penalty never rounds to 0. None (keep the flat authored value) when
        the source has no level or no size, its authored value is 0, or no override or
        fraction covers the pair. Shared by every sized source on a lane: technique buffs
        (#4594) and worn items (#4628).
        """
        if level is None or size is None or authored_value == 0:
            return None
        magnitude = self.value(level, size)
        if magnitude is None:
            return None
        return magnitude if authored_value > 0 else -magnitude

    def vow_step(self, authored_value: int, level: int, size: int, tenths: int) -> int:
        """A vow's size step on a ``size`` modifier at the vow thread's ``level`` (#4747).

        (fraction(size + 1) - fraction(size)) x width(level) x tenths / 10, rounded half up
        and signed like the authored value, so a debuff's step is a further penalty. Read
        from the fractions and the width alone, so an override row never changes it. 0 when
        either size has no fraction or the authored value is 0.
        """
        stepped = self.fractions.get(size + 1)
        base = self.fractions.get(size)
        if stepped is None or base is None or authored_value == 0:
            return 0
        step = round_half_up((stepped - base) * self.baselines.width(level) * tenths / 10)
        return step if authored_value > 0 else -step


def load_value_table(lane: str = ModifierLane.CHECK) -> ValueTable:
    """Load ``lane``'s overrides, size fractions and level baselines in three queries."""
    overrides = {
        (level, size): value
        for size, level, value in ModifierValue.objects.filter(lane=lane).values_list(
            "size", "level", "value"
        )
    }
    fractions = dict(ModifierSizeFraction.objects.filter(lane=lane).values_list("size", "fraction"))
    return ValueTable(overrides=overrides, fractions=fractions, baselines=load_baselines(lane))


def load_taper_rules(lane: str = ModifierLane.CHECK) -> dict[str, TaperRule]:
    """``lane``'s taper rules by source kind, in one query. Empty means no taper."""
    return {
        kind: TaperRule(ratio=ratio, floor=floor)
        for kind, ratio, floor in ModifierTaper.objects.filter(lane=lane).values_list(
            "source_kind", "ratio", "floor"
        )
    }


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


def load_tier_table() -> TierTable:
    """Load every ``LevelTier`` row in one query."""
    starts: list[int] = []
    totals: list[int] = []
    running = 0
    for start_level, bonus_points in LevelTier.objects.order_by("start_level").values_list(
        "start_level", "bonus_points"
    ):
        running += bonus_points
        starts.append(start_level)
        totals.append(running)
    return TierTable(starts=tuple(starts), totals=tuple(totals))


def tier_bonus(level: int, table: TierTable | None = None) -> int:
    """The tier jump a level carries: the sum of ``bonus_points`` of the tiers it has reached.

    A caller valuing many levels passes one loaded ``table`` (``load_tier_table``), as it
    would for ``load_baselines``. 0 with no tier rows.
    """
    return (load_tier_table() if table is None else table).bonus(level)


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
