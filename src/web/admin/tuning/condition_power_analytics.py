"""Condition combat-power analytics for the Game Tuning dashboard (#3390).

Wraps `world.magic.services.condition_power_eval.evaluate_all_conditions_with_reference`
into the shape the extended Conditions panel renders - mirrors
`web.admin.tuning.technique_analytics`'s two-tier caching contract exactly (see that
module's docstring): the expensive evaluator run is cached independently of the panel's
existing `danger_score` sort, and the VIEW layers its own exact-param cache on top.

`ConditionPanelRow` is the merge point the view (`tuning_conditions_fragment`) uses to
join this module's DE report per condition against the pre-existing, unchanged
`condition_analytics.compute_condition_danger` danger-score row for the SAME template
(Decision 1, issue #3390: both numbers ship side by side, DE becomes the panel's default
sort, `danger_score` stays as its own column).
"""

from __future__ import annotations

from dataclasses import dataclass

from django.core.cache import cache

from web.admin.tuning.condition_analytics import ConditionDangerRow
from world.magic.services import condition_power_eval
from world.magic.types.condition_power import ConditionPowerReport
from world.magic.types.technique_power import EvalContext, ReferenceFrame

#: 24h - mirrors `technique_analytics._CORPUS_CACHE_TIMEOUT`; a catalog-wide evaluation
#: run should outlive a single admin session.
_CORPUS_CACHE_TIMEOUT = 60 * 60 * 24

_AT_SEVERITY_DEFAULT = 5
_DURATION_ROUNDS_DEFAULT = 3
_LEVEL_DEFAULT = 10
_THREAD_LEVEL_DEFAULT = 3
_ROLLER_POINTS_DEFAULT = 25
_TARGET_DIFFICULTY_DEFAULT = 25
_ROLL_MODIFIER_DEFAULT = 0


@dataclass(frozen=True, slots=True)
class ConditionPowerAnalyticsParams:
    """Panel knobs for the Conditions tuning panel's DE column (#3390).

    Mirrors `TechniqueAnalyticsParams` - a plain, unvalidated value object. Clamping
    happens at the form/query-param boundary (`web.admin.tuning.views`).
    """

    at_severity: int = _AT_SEVERITY_DEFAULT
    duration_rounds: int = _DURATION_ROUNDS_DEFAULT
    level: int = _LEVEL_DEFAULT
    thread_level: int = _THREAD_LEVEL_DEFAULT
    roller_points: int = _ROLLER_POINTS_DEFAULT
    target_difficulty: int = _TARGET_DIFFICULTY_DEFAULT
    roll_modifier: int = _ROLL_MODIFIER_DEFAULT


@dataclass(frozen=True, slots=True)
class ConditionPanelRow:
    """One merged panel row: a condition's DE report alongside its (unchanged)
    danger-score row, joined by `ConditionTemplate.pk` (#3390, Decision 1)."""

    power: ConditionPowerReport
    danger: ConditionDangerRow | None


@dataclass(frozen=True, slots=True)
class ConditionPowerPanelData:
    """Everything the extended `_conditions_panel.html` DE column needs (#3390)."""

    #: Sorted by `total_de` desc (Decision 1: DE is the panel's default sort).
    rows: list[ConditionPowerReport]
    #: `ValuationProvenance.value -> count`, across every valuation in the corpus.
    provenance_summary: dict[str, int]
    params: ConditionPowerAnalyticsParams
    reference: ReferenceFrame


def _corpus_cache_key(params: ConditionPowerAnalyticsParams) -> str:
    """Cache key for the expensive evaluator run."""
    return (
        f"tuning-condition-power-corpus:{params.at_severity}:{params.duration_rounds}:"
        f"{params.level}:{params.thread_level}:{params.roller_points}:"
        f"{params.target_difficulty}:{params.roll_modifier}"
    )


def _provenance_summary(reports: list[ConditionPowerReport]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for report in reports:
        for valuation in report.valuations:
            key = valuation.provenance.value
            counts[key] = counts.get(key, 0) + 1
    return counts


def build_condition_power_panel(params: ConditionPowerAnalyticsParams) -> ConditionPowerPanelData:
    """Build the full Conditions DE panel payload for *params* (#3390).

    Called via the module object (never a bare `from ... import`) so tests can patch
    `condition_power_eval.evaluate_all_conditions_with_reference` at its origin and
    still intercept this call - same discipline as `technique_analytics`.
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
    reports, reference = condition_power_eval.evaluate_all_conditions_with_reference(
        context, at_severity=params.at_severity, duration_rounds=params.duration_rounds
    )
    reports_sorted = sorted(reports, key=lambda report: -report.total_de)

    panel = ConditionPowerPanelData(
        rows=reports_sorted,
        provenance_summary=_provenance_summary(reports),
        params=params,
        reference=reference,
    )
    cache.set(key, panel, _CORPUS_CACHE_TIMEOUT)
    return panel
