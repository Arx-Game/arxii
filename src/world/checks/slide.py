"""Band positions, the slide and the hopeless pin (#4601, slice b of #4551).

Every total sits part of the way through its rank band (its **band position**). The
rank difference between roller and target is therefore fractional: whole part ``lo``,
share ``f``. The roll uses result chart ``lo`` **slid** a share ``f`` of the way toward
chart ``lo + 1``:

* The slide works on the "at least X" chances of chart ``lo``'s own outcomes. Each moves
  in a straight line from chart ``lo``'s value toward chart ``lo + 1``'s.
* Where chart ``lo + 1`` has an outcome chart ``lo`` lacks, that share counts as chart
  ``lo``'s nearest outcome by success level (the lower one on a tie). So the worst
  outcomes shrink, the better ones grow, and no outcome the chart lacks appears until the
  total reaches the next rank. Critical Success (2) first appears at difference 0.

**The hopeless pin.** When the character's own standing (both sides' totals without
modifiers) lands on a chart with no outcome above success level 0 (an impossible chart,
the same test as ``chart_has_success_outcomes``), modifiers only slide the odds within
that chart, up to 100% of its band. They never lift the roll onto another chart. Net
penalties still resolve normally, onto a lower (also impossible) chart.

A difference below the lowest authored chart sits at 0% of that chart's band; one at or
above the highest authored chart uses that chart as it is. Nothing here is a tuning
number: every value comes from the ``CheckRank`` and ``ResultChart`` rows.

The roll itself is one d100 plus a fraction inside the face (``CheckRoll``), so the
continuous chance of each outcome equals exactly its share of the slid chart, and the
slide at 0% reproduces the authored chart face for face.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import TYPE_CHECKING

from world.traits.models import CheckRank, ResultChart, ResultChartOutcome

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from world.traits.models import CheckOutcome

ROLL_FACES = 100
_PERCENT = 100


@dataclass(frozen=True)
class BandPosition:
    """Where a total sits: its check rank and how far it is through that rank's band.

    ``share`` is 0 at the rank's own threshold and approaches 1 just below the next
    rank's. At the top rank there is no next rank and the share is 0. A total below every
    rank's threshold has no rank (``rank`` None, counted as rank number 0, as the whole-rank
    pipeline always did) and ``next_rank`` names the lowest rank.
    """

    points: int
    rank: CheckRank | None
    next_rank: CheckRank | None
    share: float

    @property
    def value(self) -> float:
        """The rank number plus the share, for example 3.67."""
        return (self.rank.rank if self.rank else 0) + self.share

    @property
    def percent(self) -> int:
        """The share as a whole percent, never shown as 100."""
        if self.share <= 0:
            return 0
        return min(_PERCENT - 1, max(1, round(self.share * _PERCENT)))

    @property
    def text(self) -> str:
        """For example "Expert (rank 3), 67% toward Master (rank 4)"."""
        if self.rank is None:
            if self.next_rank is not None:
                return f"Below {self.next_rank.name} (rank {self.next_rank.rank})"
            return "No rank"
        here = f"{self.rank.name} (rank {self.rank.rank})"
        if self.next_rank is None or self.percent == 0:
            return here
        return f"{here}, {self.percent}% toward {self.next_rank.name} (rank {self.next_rank.rank})"


def load_ranks() -> list[CheckRank]:
    """Every ``CheckRank`` row, lowest first: one query, shared by both sides of a check."""
    return list(CheckRank.objects.order_by("min_points"))


def band_position(points: int, ranks: Sequence[CheckRank] | None = None) -> BandPosition:
    """The band position of ``points`` against the ``CheckRank`` rows."""
    ranks = load_ranks() if ranks is None else ranks
    if not ranks:
        return BandPosition(points=points, rank=None, next_rank=None, share=0.0)
    if points < ranks[0].min_points:
        return BandPosition(points=points, rank=None, next_rank=ranks[0], share=0.0)
    index = 0
    for position, rank in enumerate(ranks):
        if rank.min_points <= points:
            index = position
    rank = ranks[index]
    next_rank = ranks[index + 1] if index + 1 < len(ranks) else None
    share = 0.0
    if next_rank is not None and points > rank.min_points:
        width = next_rank.min_points - rank.min_points
        share = min(1.0, (points - rank.min_points) / width) if width > 0 else 0.0
    return BandPosition(points=points, rank=rank, next_rank=next_rank, share=share)


@dataclass(frozen=True)
class SlidBand:
    """One outcome's share of the slid chart, as a continuous span of the roll.

    A roll position ``x`` in (0, 100] lands here when ``low < x <= high``. An authored band
    ``min_roll..max_roll`` at 0% slide is the span ``(min_roll - 1, max_roll]``.
    """

    outcome: CheckOutcome
    low: float
    high: float

    @property
    def probability(self) -> float:
        return (self.high - self.low) / ROLL_FACES


@dataclass(frozen=True)
class SlidChart:
    """A result chart slid ``share`` of the way toward ``toward``, over its own outcomes."""

    chart: ResultChart | None
    toward: ResultChart | None
    share: float
    bands: tuple[SlidBand, ...]

    def outcome_for(self, position: float) -> CheckOutcome | None:
        """The outcome a roll position in (0, 100] lands on."""
        for band in self.bands:
            if band.low < position <= band.high:
                return band.outcome
        return self.bands[-1].outcome if self.bands and position > 0 else None

    def at_least(self, success_level: int) -> float:
        """The chance of this success level or better."""
        return sum(b.probability for b in self.bands if b.outcome.success_level >= success_level)

    @property
    def best_outcome(self) -> CheckOutcome | None:
        return self.bands[-1].outcome if self.bands else None


def _level_masses(rows: Iterable[ResultChartOutcome]) -> dict[int, tuple[CheckOutcome, int]]:
    """Faces per success level on one chart (the outcome row kept for each level)."""
    masses: dict[int, tuple[CheckOutcome, int]] = {}
    for row in rows:
        level = int(row.outcome.success_level)
        faces = row.max_roll - row.min_roll + 1
        if level in masses:
            outcome, held = masses[level]
            masses[level] = (outcome, held + faces)
        else:
            masses[level] = (row.outcome, faces)
    return masses


def _nearest(level: int, levels: Sequence[int]) -> int:
    """The nearest of ``levels`` by success level, the lower one on a tie."""
    return min(levels, key=lambda candidate: (abs(candidate - level), candidate))


def slide_chart(
    chart: ResultChart | None,
    toward: ResultChart | None,
    share: float,
    rows: Sequence[ResultChartOutcome],
) -> SlidChart:
    """Slide ``chart`` a ``share`` of the way toward ``toward`` (see the module docstring).

    ``rows`` holds the outcome rows of both charts (any order); the rows of other charts
    are ignored. A chart with no rows gives a slid chart with no bands.
    """
    if chart is None:
        return SlidChart(chart=None, toward=None, share=0.0, bands=())
    own = _level_masses(row for row in rows if row.chart_id == chart.pk)
    if not own:
        return SlidChart(chart=chart, toward=toward, share=0.0, bands=())
    levels = sorted(own)
    own_total = sum(faces for _outcome, faces in own.values())

    next_masses: dict[int, float] = dict.fromkeys(levels, 0.0)
    next_total = 0
    if toward is not None and toward.pk != chart.pk and share > 0:
        for level, (_outcome, faces) in _level_masses(
            row for row in rows if row.chart_id == toward.pk
        ).items():
            next_masses[_nearest(level, levels)] += faces
            next_total += faces
    if next_total == 0:
        share = 0.0

    # Each "at least X" chance on this chart's own levels moves in a straight line toward
    # the next chart's (mapped) chance; the bands are the differences between them.
    def at_least(index: int) -> float:
        here = sum(own[lv][1] for lv in levels[index:]) / own_total
        if not next_total:
            return here
        there = sum(next_masses[lv] for lv in levels[index:]) / next_total
        return (1 - share) * here + share * there

    bands: list[SlidBand] = []
    for index, level in enumerate(levels):
        low = ROLL_FACES * (1 - at_least(index))
        high = ROLL_FACES * (1 - at_least(index + 1)) if index + 1 < len(levels) else ROLL_FACES
        if high > low:
            bands.append(SlidBand(outcome=own[level][0], low=low, high=high))
    return SlidChart(
        chart=chart, toward=toward if share > 0 else None, share=share, bands=tuple(bands)
    )


def chart_is_impossible(rows: Sequence[ResultChartOutcome], chart: ResultChart | None) -> bool:
    """True when ``chart`` has no outcome above success level 0 (or no chart at all)."""
    if chart is None:
        return True
    return not any(row.chart_id == chart.pk and row.outcome.success_level > 0 for row in rows)


@dataclass(frozen=True)
class CheckStanding:
    """Both sides' band positions, the fractional difference, and the chart the roll uses.

    ``difference`` is roller minus target with every point counted; ``own_difference``
    the same on own standing alone (no modifiers on either side). ``chart_difference`` is
    the whole difference of the chart the roll uses and ``slid.share`` how far it slides
    toward the next. ``hopeless`` is True when own standing lands on an impossible chart;
    ``pinned`` when that held the roll on its own chart against modifiers that would
    otherwise have lifted it.
    """

    roller: BandPosition
    target: BandPosition
    own_roller: BandPosition
    own_target: BandPosition
    difference: float
    own_difference: float
    chart_difference: int
    hopeless: bool
    pinned: bool
    slid: SlidChart

    @property
    def chart(self) -> ResultChart | None:
        return self.slid.chart

    @property
    def share(self) -> float:
        return self.slid.share

    @property
    def summary(self) -> str:
        """Roller against target, for result text."""
        return f"{self.roller.text} against {self.target.text}"


def _normalize(difference: float, lowest: int, highest: int) -> tuple[int, float]:
    """Whole chart difference and slide share, clamped to the authored charts."""
    if difference < lowest:
        return lowest, 0.0
    if difference >= highest:
        return highest, 0.0
    whole = math.floor(difference)
    return whole, difference - whole


def _chart_rows(*charts: ResultChart | None) -> list[ResultChartOutcome]:
    ids = {chart.pk for chart in charts if chart is not None}
    if not ids:
        return []
    return list(
        ResultChartOutcome.objects.filter(chart_id__in=ids)
        .select_related("outcome")
        .order_by("chart_id", "min_roll")
    )


def resolve_standing(
    roller_points: int,
    target_points: int,
    *,
    own_roller_points: int | None = None,
    own_target_points: int | None = None,
    ranks: Sequence[CheckRank] | None = None,
) -> CheckStanding:
    """Band positions, the slide and the hopeless pin for one check, without rolling.

    ``roller_points`` and ``target_points`` count everything. ``own_roller_points`` and
    ``own_target_points`` are the same totals without modifiers; ``None`` means the side
    carries no modifiers.
    """
    ranks = load_ranks() if ranks is None else ranks
    own_roller_points = roller_points if own_roller_points is None else own_roller_points
    own_target_points = target_points if own_target_points is None else own_target_points
    roller = band_position(roller_points, ranks)
    target = band_position(target_points, ranks)
    own_roller = band_position(own_roller_points, ranks)
    own_target = band_position(own_target_points, ranks)
    difference = roller.value - target.value
    own_difference = own_roller.value - own_target.value

    authored = ResultChart.authored_range()
    if authored is None:
        empty = SlidChart(chart=None, toward=None, share=0.0, bands=())
        return CheckStanding(
            roller=roller,
            target=target,
            own_roller=own_roller,
            own_target=own_target,
            difference=difference,
            own_difference=own_difference,
            chart_difference=math.floor(difference),
            hopeless=False,
            pinned=False,
            slid=empty,
        )
    lowest, highest = authored

    own_whole, _own_share = _normalize(own_difference, lowest, highest)
    own_chart = ResultChart.get_chart_for_difference(own_whole)
    own_rows = _chart_rows(own_chart)
    hopeless = chart_is_impossible(own_rows, own_chart)

    whole, share = _normalize(difference, lowest, highest)
    pinned = hopeless and whole > own_whole
    if pinned:
        # The pin: modifiers slide within the own-standing chart, to at most its full
        # band, and never lift the roll onto a higher chart. Anything that stays on or
        # below the own-standing chart resolves exactly as it would unpinned.
        whole, share = own_whole, 1.0
    chart = ResultChart.get_chart_for_difference(whole)
    toward = ResultChart.get_chart_for_difference(whole + 1) if share > 0 else None
    rows = own_rows if chart is own_chart and toward is None else _chart_rows(chart, toward)
    return CheckStanding(
        roller=roller,
        target=target,
        own_roller=own_roller,
        own_target=own_target,
        difference=difference,
        own_difference=own_difference,
        chart_difference=whole,
        hopeless=hopeless,
        pinned=pinned,
        slid=slide_chart(chart, toward, share, rows),
    )


@dataclass(frozen=True)
class CheckRoll:
    """One d100 roll: the whole face (after rollmod, clamped 1 to 100) and a fraction.

    ``position`` is the continuous point the roll lands on, in (0, 100]: the face minus
    the fraction. So a face lands exactly where it always did on an unslid chart.
    """

    face: int
    fraction: float

    @property
    def position(self) -> float:
        return self.face - self.fraction
