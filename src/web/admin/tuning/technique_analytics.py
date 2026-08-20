"""Technique combat-power analytics for the Game Tuning dashboard (#3279 Task 3).

Wraps `world.magic.services.technique_power_eval.evaluate_all_with_reference` - the
DE (damage-equivalent per cast) evaluator built in Tasks 1-2 - into the shapes the
Techniques panel renders: a sortable league table, a bucket for unpriced/zero-value
techniques, and a provenance-count summary. See
`docs/plans/3279-technique-power-eval-plan.md` for the full currency spec this
panel surfaces.

**Two-tier caching.** Evaluating ~270 techniques with DB lookups per cast band is
too slow to run on every page load or every header-sort click, so the expensive
step (:func:`_evaluate_corpus`, everything but `sort`) is cached independently of
`sort` via Django's cache - a sort-only re-render (a GET carrying a new `?sort=`)
reuses the cached corpus and only re-buckets/re-sorts, which is cheap. The VIEW
(`web.admin.tuning.views.tuning_techniques_fragment`) layers its own exact-param
cache on top of the full `TechniquePanelData` this module returns, mirroring the
simulation panel's cache-key/last-key-pointer contract - see that view's docstring.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.core.cache import cache

from world.magic.services import technique_power_eval
from world.magic.types.technique_power import (
    EvalContext,
    ReferenceFrame,
    TechniquePowerReport,
)

#: Sort-key identifiers, named constants (not bare string literals) so the
#: comparisons in `_sort_value` don't trip `tools/lint_string_literal.py`.
SORT_BASELINE_DE = "baseline_de"
SORT_AMPLIFIED_DE = "amplified_de"
SORT_DE_PER_ANIMA = "de_per_anima"
SORT_NAME = "name"
SORT_LEVEL = "level"

#: Whitelisted `sort` values - anything else falls back to `DEFAULT_SORT` rather
#: than erroring, since a header-link GET has no error-feedback surface.
SORT_KEYS = frozenset(
    {SORT_BASELINE_DE, SORT_AMPLIFIED_DE, SORT_DE_PER_ANIMA, SORT_NAME, SORT_LEVEL}
)
DEFAULT_SORT = SORT_BASELINE_DE

_LEVEL_DEFAULT = 10
_THREAD_LEVEL_DEFAULT = 3
_ROLLER_POINTS_DEFAULT = 25
_TARGET_DIFFICULTY_DEFAULT = 25
_ROLL_MODIFIER_DEFAULT = 0

#: 24h - matches `_SIMULATION_CACHE_TIMEOUT` in `web.admin.tuning.views`; a
#: catalog-wide evaluation run should outlive a single admin session.
_CORPUS_CACHE_TIMEOUT = 60 * 60 * 24


def resolve_sort_key(sort: str) -> str:
    """Whitelist-or-fallback for a `sort` value (query param or form input)."""
    return sort if sort in SORT_KEYS else DEFAULT_SORT


@dataclass(frozen=True, slots=True)
class TechniqueAnalyticsParams:
    """Panel knobs for the Techniques tuning panel (#3279 Task 3).

    Mirrors `SimulationParams` (`world.combat.simulation`) - a plain, unvalidated
    value object. Clamping/whitelisting happens at the form boundary
    (`web.admin.tuning.views.TechniqueAnalyticsForm`) and, for `sort` specifically,
    also in :func:`resolve_sort_key` (reused for the header-link GET path, which
    never touches the form).
    """

    level: int = _LEVEL_DEFAULT
    thread_level: int = _THREAD_LEVEL_DEFAULT
    roller_points: int = _ROLLER_POINTS_DEFAULT
    target_difficulty: int = _TARGET_DIFFICULTY_DEFAULT
    roll_modifier: int = _ROLL_MODIFIER_DEFAULT
    sort: str = DEFAULT_SORT


@dataclass(frozen=True, slots=True)
class TechniqueRow:
    """One league-table row: a report plus its derived amplification ratio."""

    report: TechniquePowerReport
    #: `amplified_de / baseline_de`, or `None` when `baseline_de` is 0 (undefined).
    amplification_ratio: float | None


@dataclass(frozen=True, slots=True)
class TechniquePanelData:
    """Everything the `_techniques_panel.html` fragment renders (#3279 Task 3)."""

    rows: list[TechniqueRow]
    #: Reports with `baseline_de == 0` and every valuation zero - unpriced/inert
    #: content (UNPRICEABLE/INERT_PAYLOAD-only techniques, or ones with no
    #: `ResultChart` to roll against at all).
    zero_bucket: list[TechniquePowerReport]
    #: `ValuationProvenance.value -> count`, across every valuation in the corpus
    #: (both `rows` and `zero_bucket`).
    provenance_summary: dict[str, int]
    params: TechniqueAnalyticsParams
    reference: ReferenceFrame


def _corpus_cache_key(params: TechniqueAnalyticsParams) -> str:
    """Cache key for the expensive evaluator run - deliberately excludes `sort`."""
    return (
        f"tuning-tech-power-corpus:{params.level}:{params.thread_level}:"
        f"{params.roller_points}:{params.target_difficulty}:{params.roll_modifier}"
    )


def _evaluate_corpus(
    params: TechniqueAnalyticsParams,
) -> tuple[list[TechniquePowerReport], ReferenceFrame]:
    """Run (or reuse a cached) `evaluate_all_with_reference` for *params* (#3279).

    Called via the module object (`technique_power_eval.evaluate_all_with_reference`,
    never a bare `from ... import`) so tests can patch it at its origin and still
    intercept this call.
    """
    key = _corpus_cache_key(params)
    cached = cache.get(key)
    if cached is not None:
        return cached

    context = EvalContext(
        level=params.level,
        thread_level=params.thread_level,
        roller_points=params.roller_points,
        target_difficulty=params.target_difficulty,
        roll_modifier=params.roll_modifier,
    )
    result = technique_power_eval.evaluate_all_with_reference(context)
    cache.set(key, result, _CORPUS_CACHE_TIMEOUT)
    return result


def _is_zero_value(report: TechniquePowerReport) -> bool:
    """True when a report has nothing priced: baseline_de is 0 and every valuation is 0."""
    return report.baseline_de == 0 and all(v.value == 0 for v in report.valuations)


def _amplification_ratio(report: TechniquePowerReport) -> float | None:
    if report.baseline_de > 0:
        return report.amplified_de / report.baseline_de
    return None


def _sort_value(row: TechniqueRow, sort: str) -> object:
    """Sort key for one row - numeric sorts descending (best first), name ascending."""
    report = row.report
    if sort == SORT_NAME:
        return report.name.lower()
    if sort == SORT_LEVEL:
        return -report.level
    if sort == SORT_AMPLIFIED_DE:
        return -report.amplified_de
    if sort == SORT_DE_PER_ANIMA:
        return -report.de_per_anima
    return -report.baseline_de


def _provenance_summary(reports: list[TechniquePowerReport]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for report in reports:
        for valuation in report.valuations:
            key = valuation.provenance.value
            counts[key] = counts.get(key, 0) + 1
    return counts


def build_technique_panel(params: TechniqueAnalyticsParams) -> TechniquePanelData:
    """Build the full Techniques panel payload for *params* (#3279 Task 3).

    Splits the evaluated corpus into priced rows (sorted per
    `resolve_sort_key(params.sort)`) and the zero/unpriced bucket, and tallies
    valuation provenance across the whole corpus. The expensive evaluator run
    itself is cached independently of `sort` - see :func:`_evaluate_corpus`.
    """
    reports, reference = _evaluate_corpus(params)

    rows: list[TechniqueRow] = []
    zero_bucket: list[TechniquePowerReport] = []
    for report in reports:
        if _is_zero_value(report):
            zero_bucket.append(report)
        else:
            ratio = _amplification_ratio(report)
            rows.append(TechniqueRow(report=report, amplification_ratio=ratio))

    sort = resolve_sort_key(params.sort)
    rows.sort(key=lambda row: _sort_value(row, sort))

    return TechniquePanelData(
        rows=rows,
        zero_bucket=zero_bucket,
        provenance_summary=_provenance_summary(reports),
        params=params,
        reference=reference,
    )
