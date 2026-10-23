"""Check-success-by-tier analytics for the Game Tuning dashboard (#1221 Task 2).

Tallies the exact probability distribution the check engine produces for each
`ResultChart`, without reimplementing (or approximating) its rules: for every
possible roll 1..100 we apply the same clamp the engine applies
(`world.checks.services.perform_check`, lines 92-96) and look up the same
`ResultChartOutcome` row it would land in. `compute_matchup` derives its
rank_difference the same way `_compute_check_breakdown`
(`world.checks.services.py:170-180`) does, so the "what happens for this
specific roller/target pair" sub-panel mirrors production exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Prefetch

from world.checks.constants import ModifierSourceKind
from world.checks.modifier_values import (
    level_baseline,
    load_taper_rules,
    load_value_table,
    rank_band_share,
)
from world.checks.types import ModifierBreakdown, ModifierContribution
from world.traits.models import CheckRank, ResultChart, ResultChartOutcome

_ROLL_RANGE = range(1, 101)


@dataclass(frozen=True)
class OutcomeBand:
    """One `CheckOutcome`'s share of the 1-100 roll space for a single chart."""

    name: str
    success_level: int
    probability: float  # 0.0-1.0


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


def compute_matchup(
    *, roller_points: int, target_difficulty: int, roll_modifier: int = 0
) -> ChartDistribution | None:
    """Single-chart distribution for a specific roller-points/target-difficulty matchup.

    Derives rank_difference exactly as `_compute_check_breakdown` does: a missing
    rank (roller or target below every `CheckRank.min_points`) contributes 0. The
    *returned* `rank_difference` is always this derived roller-minus-target value —
    even when `ResultChart.get_chart_for_difference` falls back to the nearest
    seeded chart because there's no exact match, the derived difference (not the
    fallback chart's own `rank_difference` field) is what's reported, so the UI
    reflects the true matchup. `chart_name` still names the fallback-selected
    chart, so the fallback itself stays visible. Returns `None` only when no
    `ResultChart` exists at all.
    """
    roller_rank = CheckRank.get_rank_for_points(roller_points)
    target_rank = CheckRank.get_rank_for_points(target_difficulty)
    rank_difference = (roller_rank.rank if roller_rank else 0) - (
        target_rank.rank if target_rank else 0
    )

    chart = ResultChart.get_chart_for_difference(rank_difference)
    if chart is None:
        return None
    outcome_rows = list(
        ResultChartOutcome.objects.filter(chart=chart)
        .select_related("outcome")
        .order_by("min_roll")
    )
    return _distribution_for_chart(
        chart, outcome_rows, roll_modifier=roll_modifier, rank_difference=rank_difference
    )


@dataclass(frozen=True)
class ModifierPileReport:
    """What a pile of equal check modifiers does at one character level (#4594).

    The check lane's piece of the simulator: ``count`` modifiers of one level and size,
    each valued by the value table, tapered as CONDITION contributions, laid on a
    character whose own total is the level baseline, against a target at that same
    baseline. The odds use whole rank differences until the slide lands (#4551 slice b).
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
        buffed=compute_matchup(roller_points=baseline + tapered, target_difficulty=baseline),
    )
