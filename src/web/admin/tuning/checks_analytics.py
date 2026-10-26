"""Check-success-by-tier analytics for the Game Tuning dashboard (#1221 Task 2).

Tallies the exact probability distribution the check engine produces for each
`ResultChart`, without reimplementing (or approximating) its rules: for every
possible roll 1..100 we apply the same clamp the engine applies
(`world.checks.services.perform_check`, lines 92-96) and look up the same
`ResultChartOutcome` row it would land in. `compute_matchup` derives its
rank_difference the same way `_compute_check_breakdown`
(`world.checks.services.py:170-180`) does, so the "what happens for this
specific roller/target pair" sub-panel mirrors production exactly.

Since #4601 the matchup reads the slid chart the engine itself builds
(`world.checks.slide.resolve_standing`): band positions and the slide toward the next
chart, from both sides' full totals (#4723). `compute_slide_table` shows the
slide at 0%, 25%, 50%, 75% and 100% through every chart's band. Nothing here
reimplements the slide; it only tallies the engine's own slid bands under a roll
modifier.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from itertools import pairwise
from typing import TYPE_CHECKING

from django.db.models import Prefetch

from world.checks.constants import ModifierSourceKind
from world.checks.modifier_values import (
    level_baseline,
    load_taper_rules,
    load_value_table,
    rank_band_share,
)
from world.checks.slide import load_ranks, resolve_standing, slide_chart
from world.checks.types import ModifierBreakdown, ModifierContribution
from world.traits.models import CheckRank, ResultChart, ResultChartOutcome

if TYPE_CHECKING:
    from world.checks.slide import CheckStanding, SlidChart

_ROLL_RANGE = range(1, 101)


@dataclass(frozen=True)
class OutcomeBand:
    """One `CheckOutcome`'s share of the 1-100 roll space for a single chart."""

    name: str
    success_level: int
    probability: float  # 0.0-1.0

    @property
    def percent(self) -> str:
        """The probability as a percent to one decimal, for example "30.6%" (#4601)."""
        value = round(self.probability * 100, 1)
        return f"{value:g}%"


@dataclass(frozen=True)
class ChartDistribution:
    """Full probability breakdown for one `ResultChart` under a given roll_modifier.

    `rank_difference` is the chart's own field in `compute_chart_distributions`
    results, but is the *derived* roller-minus-target rank difference in
    `compute_matchup` results (which can differ from `chart_name`'s chart when
    `ResultChart.get_chart_for_difference` falls back to the nearest chart).
    """

    rank_difference: int
    chart_name: str
    bands: list[OutcomeBand]
    success_probability: float  # P(success_level > 0)
    expected_success_level: float
    standing: CheckStanding | None = None  # #4601: set on matchups


def _tally_outcomes(
    outcome_rows: list[ResultChartOutcome], *, roll_modifier: int
) -> list[OutcomeBand]:
    """Tally outcome probabilities for one chart's rows by walking every possible roll.

    Mirrors the engine exactly: `effective = max(1, min(100, roll + roll_modifier))`,
    then find the `ResultChartOutcome` whose `[min_roll, max_roll]` contains it.
    """
    counts: dict[int, int] = {}
    names: dict[int, str] = {}
    levels: dict[int, int] = {}
    for roll in _ROLL_RANGE:
        effective = max(1, min(100, roll + roll_modifier))
        matched = next(
            (row for row in outcome_rows if row.min_roll <= effective <= row.max_roll),
            None,
        )
        if matched is None:
            continue
        key = matched.outcome_id
        counts[key] = counts.get(key, 0) + 1
        names[key] = matched.outcome.name
        levels[key] = matched.outcome.success_level

    bands = [
        OutcomeBand(name=names[key], success_level=levels[key], probability=count / 100.0)
        for key, count in counts.items()
    ]
    bands.sort(key=lambda band: band.success_level, reverse=True)
    return bands


def _distribution_for_chart(
    chart: ResultChart,
    outcome_rows: list[ResultChartOutcome],
    *,
    roll_modifier: int,
    rank_difference: int | None = None,
) -> ChartDistribution:
    """Break one chart down into bands.

    ``rank_difference`` defaults to the chart's own field. ``compute_matchup``
    passes the *derived* roller-minus-target difference instead, because
    ``get_chart_for_difference`` may have fallen back to a neighbouring chart
    whose own field would then be wrong.
    """
    bands = _tally_outcomes(outcome_rows, roll_modifier=roll_modifier)
    success_probability = sum(band.probability for band in bands if band.success_level > 0)
    expected_success_level = sum(band.success_level * band.probability for band in bands)
    return ChartDistribution(
        rank_difference=chart.rank_difference if rank_difference is None else rank_difference,
        chart_name=chart.name,
        bands=bands,
        success_probability=success_probability,
        expected_success_level=expected_success_level,
    )


def compute_chart_distributions(*, roll_modifier: int = 0) -> list[ChartDistribution]:
    """Probability breakdown for every seeded `ResultChart`, ordered by rank_difference."""
    charts = ResultChart.objects.prefetch_related(
        Prefetch(
            "outcomes",
            queryset=ResultChartOutcome.objects.select_related("outcome").order_by("min_roll"),
            to_attr="cached_outcomes",
        )
    ).order_by("rank_difference")
    return [
        _distribution_for_chart(chart, chart.cached_outcomes, roll_modifier=roll_modifier)
        for chart in charts
    ]


def _tally_slid(slid: SlidChart, *, roll_modifier: int) -> list[OutcomeBand]:
    """Exact outcome odds on a slid chart under a roll modifier, as the engine rolls.

    The engine clamps ``roll + roll_modifier`` to a face 1 to 100 and reads the slid
    chart at a uniformly random point inside that face (``world.checks.slide.CheckRoll``),
    so each face contributes its overlap with each band.
    """
    shares: dict[int, float] = {}
    for roll in _ROLL_RANGE:
        face = max(1, min(100, roll + roll_modifier))
        for index, band in enumerate(slid.bands):
            overlap = min(face, band.high) - max(face - 1, band.low)
            if overlap > 0:
                shares[index] = shares.get(index, 0.0) + overlap / 100.0
    bands = [
        OutcomeBand(
            name=slid.bands[index].outcome.name,
            success_level=slid.bands[index].outcome.success_level,
            probability=probability,
        )
        for index, probability in shares.items()
    ]
    bands.sort(key=lambda band: band.success_level, reverse=True)
    return bands


def _distribution_for_slid(
    slid: SlidChart,
    *,
    roll_modifier: int,
    rank_difference: int,
    standing: CheckStanding | None = None,
) -> ChartDistribution:
    bands = _tally_slid(slid, roll_modifier=roll_modifier)
    return ChartDistribution(
        rank_difference=rank_difference,
        chart_name=slid.chart.name if slid.chart else "",
        bands=bands,
        success_probability=sum(b.probability for b in bands if b.success_level > 0),
        expected_success_level=sum(b.success_level * b.probability for b in bands),
        standing=standing,
    )


def compute_matchup(
    *,
    roller_points: int,
    target_difficulty: int,
    roll_modifier: int = 0,
    modifier_points: int = 0,
    target_modifier_points: int = 0,
) -> ChartDistribution | None:
    """Distribution for one roller/target matchup, exactly as ``perform_check`` rolls it.

    ``roller_points`` and ``target_difficulty`` are each side's own standing;
    ``modifier_points`` is added to the roller as modifiers (a pile of buffs) and
    ``target_modifier_points`` to the target (positive buffs it, negative debuffs it).
    The engine's ``resolve_standing`` decides the band positions and the slide from the
    full totals (#4723); the result carries it as ``standing``. ``rank_difference`` is the
    whole difference of the chart the roll uses, which may differ from ``chart_name``'s
    chart field when the lookup falls back to the nearest authored chart. Returns
    ``None`` only when no ``ResultChart`` exists at all.
    """
    standing = resolve_standing(
        roller_points + modifier_points, target_difficulty + target_modifier_points
    )
    if standing.chart is None:
        return None
    return _distribution_for_slid(
        standing.slid,
        roll_modifier=roll_modifier,
        rank_difference=standing.chart_difference,
        standing=standing,
    )


SLIDE_SHARES: tuple[float, ...] = (0.0, 0.25, 0.5, 0.75, 1.0)


@dataclass(frozen=True)
class SlideRow:
    """One chart's odds at each share of the way through its band (#4601)."""

    rank_difference: int
    chart_name: str
    toward_name: str
    impossible: bool
    steps: list[ChartDistribution]


def compute_slide_table(*, roll_modifier: int = 0) -> list[SlideRow]:
    """The slide at 0%, 25%, 50%, 75% and 100% through every authored chart's band.

    The highest chart has nothing to slide toward and is left out. Built from the same
    ``slide_chart`` the roll uses.
    """
    charts = list(ResultChart.objects.order_by("rank_difference"))
    rows = list(ResultChartOutcome.objects.select_related("outcome").order_by("min_roll"))
    table: list[SlideRow] = []
    for chart, toward in pairwise(charts):
        steps = [
            _distribution_for_slid(
                slide_chart(chart, toward, share, rows),
                roll_modifier=roll_modifier,
                rank_difference=chart.rank_difference,
            )
            for share in SLIDE_SHARES
        ]
        impossible = not any(
            row.chart_id == chart.pk and row.outcome.success_level > 0 for row in rows
        )
        table.append(
            SlideRow(
                rank_difference=chart.rank_difference,
                chart_name=chart.name,
                toward_name=toward.name,
                impossible=impossible,
                steps=steps,
            )
        )
    return table


def rank_ladder() -> list[str]:
    """Every check rank with its number and threshold, for the panel's key."""
    return [f"{rank.name} (rank {rank.rank}): {rank.min_points}+" for rank in load_ranks()]


@dataclass(frozen=True)
class ChartChecks:
    """The chart guard, as the panel shows it (#4601; the test guard is
    ``world/checks/tests/test_slide.py`` and ``test_chart_direction.py``).

    ``impossible`` names the charts with no Success (1); ``impossible_above_winnable``
    any of them sitting above a winnable chart; ``monotonic_failures`` every "at least X"
    chance that falls from one chart to the next; ``lowest`` the lowest chart, where every
    difference below it lands at 0% of its band.
    """

    impossible: list[str]
    impossible_above_winnable: list[str]
    monotonic_failures: list[str]
    lowest: str


def compute_chart_checks() -> ChartChecks:
    """Run the monotonic and impossible-zone checks over the authored chart rows."""
    charts = list(ResultChart.objects.order_by("rank_difference"))
    rows = list(ResultChartOutcome.objects.select_related("outcome"))
    levels = sorted({row.outcome.success_level for row in rows})

    def at_least(chart: ResultChart, level: int) -> int:
        return sum(
            row.max_roll - row.min_roll + 1
            for row in rows
            if row.chart_id == chart.pk and row.outcome.success_level >= level
        )

    def label(chart: ResultChart) -> str:
        return f"{chart.name} ({chart.rank_difference})"

    impossible = [chart for chart in charts if at_least(chart, 1) == 0]
    seen_winnable = False
    above_winnable: list[str] = []
    for chart in charts:
        if chart in impossible:
            if seen_winnable:
                above_winnable.append(label(chart))
        else:
            seen_winnable = True
    failures = [
        f"at least success level {level} falls from {label(lower)} ({at_least(lower, level)}%)"
        f" to {label(higher)} ({at_least(higher, level)}%)"
        for lower, higher in pairwise(charts)
        for level in levels[1:]
        if at_least(higher, level) < at_least(lower, level)
    ]
    return ChartChecks(
        impossible=[label(chart) for chart in impossible],
        impossible_above_winnable=above_winnable,
        monotonic_failures=failures,
        lowest=label(charts[0]) if charts else "",
    )


@dataclass(frozen=True)
class ModifierPileReport:
    """What a pile of equal check modifiers does at one character level (#4594).

    The check lane's piece of the simulator: ``count`` modifiers of one level and size,
    each valued by the value table, tapered as CONDITION contributions, laid on a
    character whose own total is the level baseline, against a target at that same
    baseline. The odds are the engine's own (#4601): the baseline plus the tapered pile
    slides by band position, and a big enough pile lifts the roll onto a higher chart
    (#4723).
    """

    baseline: int
    modifier_value: int
    band_share: Decimal | None
    plain_total: int
    tapered_total: int
    rank_before: str
    rank_after: str
    unbuffed: ChartDistribution | None
    buffed: ChartDistribution | None


def _rank_name(points: int) -> str:
    rank = CheckRank.get_rank_for_points(points)
    return f"{rank.name} (rank {rank.rank})" if rank else "below every rank"


def compute_modifier_pile(
    *, character_level: int, modifier_level: int, size: int, count: int
) -> ModifierPileReport | None:
    """Simulate ``count`` modifiers of (``modifier_level``, ``size``) on one character.

    None when the value table or level baseline has no row covering the inputs; the
    panel says which rows to author.
    """
    baseline = level_baseline(character_level)
    value = load_value_table().value(modifier_level, size)
    if baseline is None or value is None:
        return None
    tapers = load_taper_rules()
    breakdown = ModifierBreakdown(
        contributions=[
            ModifierContribution(
                source_kind=ModifierSourceKind.CONDITION,
                source_label=f"Buff {index + 1}",
                value=value,
                level=modifier_level,
                size=size,
            )
            for index in range(count)
        ],
        tapers={
            kind: rule for kind, rule in tapers.items() if kind == ModifierSourceKind.CONDITION
        },
    )
    tapered = breakdown.total
    return ModifierPileReport(
        baseline=baseline,
        modifier_value=value,
        band_share=rank_band_share(value, baseline),
        plain_total=value * count,
        tapered_total=tapered,
        rank_before=_rank_name(baseline),
        rank_after=_rank_name(baseline + tapered),
        unbuffed=compute_matchup(roller_points=baseline, target_difficulty=baseline),
        buffed=compute_matchup(
            roller_points=baseline, target_difficulty=baseline, modifier_points=tapered
        ),
    )
