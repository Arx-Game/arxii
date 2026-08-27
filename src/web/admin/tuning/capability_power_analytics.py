"""Capability combat-power analytics for the Game Tuning dashboard (#3390).

Wraps `world.magic.services.capability_power_eval.evaluate_all_capabilities_with_reference`
into the shape the new Capabilities panel renders - a sortable league table, a bucket for
unpriced (`no_authored_bridge`) capabilities, and a provenance-count summary. Mirrors
`web.admin.tuning.technique_analytics`'s two-tier caching contract exactly (see that
module's docstring for the full rationale).
"""

from __future__ import annotations

from dataclasses import dataclass

from django.core.cache import cache

from world.magic.services import capability_power_eval
from world.magic.services.capability_power_eval import NO_AUTHORED_BRIDGE_FLAG
from world.magic.types.capability_power import CapabilityPowerReport
from world.magic.types.technique_power import EvalContext, ReferenceFrame

#: 24h - mirrors `technique_analytics._CORPUS_CACHE_TIMEOUT`.
_CORPUS_CACHE_TIMEOUT = 60 * 60 * 24

_LEVEL_DEFAULT = 10
_THREAD_LEVEL_DEFAULT = 3
_ROLLER_POINTS_DEFAULT = 25
_TARGET_DIFFICULTY_DEFAULT = 25
_ROLL_MODIFIER_DEFAULT = 0


@dataclass(frozen=True, slots=True)
class CapabilityPowerAnalyticsParams:
    """Panel knobs for the Capabilities tuning panel (#3390).

    Mirrors `TechniqueAnalyticsParams` - a plain, unvalidated value object. Clamping
    happens at the form/query-param boundary (`web.admin.tuning.views`). Capabilities
    have no severity/duration axis of their own (unlike conditions) - only the shared
    `EvalContext` matchup knobs.
    """

    level: int = _LEVEL_DEFAULT
    thread_level: int = _THREAD_LEVEL_DEFAULT
    roller_points: int = _ROLLER_POINTS_DEFAULT
    target_difficulty: int = _TARGET_DIFFICULTY_DEFAULT
    roll_modifier: int = _ROLL_MODIFIER_DEFAULT


@dataclass(frozen=True, slots=True)
class CapabilityPowerPanelData:
    """Everything the `_capabilities_panel.html` fragment renders (#3390)."""

    #: Priced rows (`total_de != 0`), sorted `total_de` desc.
    rows: list[CapabilityPowerReport]
    #: Reports with `total_de == 0` - today this is EVERY capability (Decision 5: no
    #: production seeder authors `CheckTypeCapabilityModifier` rows yet).
    zero_bucket: list[CapabilityPowerReport]
    #: `ValuationProvenance.value -> count`, across every valuation in the corpus.
    provenance_summary: dict[str, int]
    params: CapabilityPowerAnalyticsParams
    reference: ReferenceFrame


def _corpus_cache_key(params: CapabilityPowerAnalyticsParams) -> str:
    """Cache key for the expensive evaluator run."""
    return (
        f"tuning-capability-power-corpus:{params.level}:{params.thread_level}:"
        f"{params.roller_points}:{params.target_difficulty}:{params.roll_modifier}"
    )


def _is_zero_value(report: CapabilityPowerReport) -> bool:
    """True when a report has nothing priced (mirrors `technique_analytics._is_zero_value`)."""
    return report.total_de == 0 and all(v.value == 0 for v in report.valuations)


def _provenance_summary(reports: list[CapabilityPowerReport]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for report in reports:
        for valuation in report.valuations:
            key = valuation.provenance.value
            counts[key] = counts.get(key, 0) + 1
    return counts


def build_capability_power_panel(
    params: CapabilityPowerAnalyticsParams,
) -> CapabilityPowerPanelData:
    """Build the full Capabilities panel payload for *params* (#3390).

    Called via the module object (never a bare `from ... import`) so tests can patch
    `capability_power_eval.evaluate_all_capabilities_with_reference` at its origin and
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
    reports, reference = capability_power_eval.evaluate_all_capabilities_with_reference(context)

    rows: list[CapabilityPowerReport] = []
    zero_bucket: list[CapabilityPowerReport] = []
    for report in reports:
        if _is_zero_value(report) or NO_AUTHORED_BRIDGE_FLAG in report.flags:
            zero_bucket.append(report)
        else:
            rows.append(report)
    rows.sort(key=lambda report: -report.total_de)

    panel = CapabilityPowerPanelData(
        rows=rows,
        zero_bucket=zero_bucket,
        provenance_summary=_provenance_summary(reports),
        params=params,
        reference=reference,
    )
    cache.set(key, panel, _CORPUS_CACHE_TIMEOUT)
    return panel
