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

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from django.core.cache import cache

from world.character_creation.constants import REQUIRED_STATS, STAT_DEFAULT_VALUE
from world.character_creation.models import Beginnings
from world.checks.constants import LEVEL_POINTS_PER_LEVEL
from world.classes.models import Path
from world.magic.models import PathGiftGrant
from world.magic.models.gifts import Gift, Tradition
from world.magic.models.techniques import Technique
from world.magic.services import cg_catalog, de_valuation, technique_power_eval
from world.magic.services.technique_effects import technique_catalog_revision
from world.magic.types.technique_power import (
    FLAG_NOT_CASTABLE_STANDALONE,
    EvalContext,
    ReferenceFrame,
    TechniquePowerReport,
)
from world.species.models import Species
from world.traits.constants import STAT_DISPLAY_DIVISOR, TraitType
from world.traits.models import PointConversionRange

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
class TechniqueValuationTotals:
    """Panel-wide DE totals split by confidence instead of hiding estimates."""

    formula_baseline_de: float = 0.0
    estimated_baseline_de: float = 0.0
    formula_amplified_de: float = 0.0
    estimated_amplified_de: float = 0.0


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
    totals: TechniqueValuationTotals = field(default_factory=TechniqueValuationTotals)


def _corpus_cache_key(params: TechniqueAnalyticsParams) -> str:
    """Cache key for the expensive evaluator run - deliberately excludes `sort`.

    Carries the technique catalog's revision (#3682). Without it the key was the
    numeric knobs alone, so re-submitting the same parameters after editing a
    technique served the 24h-old corpus: staff tuned against the numbers they had
    just changed and saw no movement. `bump_technique_catalog_revision` runs on
    every authoring write, so an edit changes this key and the next run rebuilds.
    """
    return (
        f"tuning-tech-power-corpus:{technique_catalog_revision()}:"
        f"{params.level}:{params.thread_level}:"
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
    totals = TechniqueValuationTotals(
        formula_baseline_de=sum(report.formula_baseline_de for report in reports),
        estimated_baseline_de=sum(report.estimated_baseline_de for report in reports),
        formula_amplified_de=sum(report.formula_amplified_de for report in reports),
        estimated_amplified_de=sum(report.estimated_amplified_de for report in reports),
    )

    return TechniquePanelData(
        rows=rows,
        zero_bucket=zero_bucket,
        provenance_summary=_provenance_summary(reports),
        params=params,
        reference=reference,
        totals=totals,
    )


def starting_stats_roller_points(stats: dict[str, int]) -> int:
    """Convert CG display-scale stats to a representative level-one check pool.

    A technique has no single check type, so the kit report uses the mean of the
    twelve starting stat pools plus the level-one floor. This preserves the real
    CG allocation (rather than the catalog's level-10 anchor) while keeping the
    report honest about being a representative combat context.
    """
    values = [stats.get(name, STAT_DEFAULT_VALUE) for name in REQUIRED_STATS]
    converted = [
        PointConversionRange.calculate_points(TraitType.STAT, value * STAT_DISPLAY_DIVISOR)
        for value in values
    ]
    if not any(converted):
        converted = [value * STAT_DISPLAY_DIVISOR for value in values]
    return round(sum(converted) / len(converted)) + LEVEL_POINTS_PER_LEVEL


#: The context a character has at the end of character creation (#3716 Decision 2).
STARTING_LEVEL = 1
STARTING_THREAD_LEVEL = 0
#: Upper bound on extra technique picks staff can enter; distinctions grant few.
MAX_EXTRA_PICKS = 5

#: Valuation kinds that count toward the combat floor (#3716 P3).
VALUATION_KIND_DAMAGE = "damage"
PROTECTION_VALUATION_KINDS = frozenset({"mitigation", "heal"})


class OptionSource(StrEnum):
    """Where a starting-kit option comes from in character creation."""

    PATH = "path"
    TRADITION = "tradition"
    SPECIES = "species"


@dataclass(frozen=True, slots=True)
class FloorResult:
    """Whether a set of options holds a damage option and a protection option."""

    has_damage: bool
    has_protection: bool

    @property
    def met(self) -> bool:
        return self.has_damage and self.has_protection


def meets_combat_floor(reports: Iterable[TechniquePowerReport]) -> FloorResult:
    """Judge options against the combat floor (#3716 P3).

    Damage counts when any `damage` valuation is above 0; protection when any
    `mitigation` or `heal` valuation is above 0. Debuffs and control count for neither.
    """
    has_damage = False
    has_protection = False
    for report in reports:
        for valuation in report.valuations:
            if valuation.value <= 0:
                continue
            if valuation.kind == VALUATION_KIND_DAMAGE:
                has_damage = True
            elif valuation.kind in PROTECTION_VALUATION_KINDS:
                has_protection = True
    return FloorResult(has_damage=has_damage, has_protection=has_protection)


def is_castable(report: TechniquePowerReport) -> bool:
    """True when the technique carries an action template (no not-castable flag)."""
    return FLAG_NOT_CASTABLE_STANDALONE not in report.flags


def is_mostly_estimate(report: TechniquePowerReport) -> bool:
    """True when estimates are more than half of an option's baseline DE (#3716 P7)."""
    return report.baseline_de > 0 and report.estimated_baseline_de > report.baseline_de / 2


@dataclass(frozen=True, slots=True)
class StartingKitParams:
    """One character-creation combination to price (#3716)."""

    beginning: Beginnings
    tradition: Tradition
    path: Path
    gift: Gift
    species: Species | None = None
    extra_picks: int = 0
    #: Display-scale stats by name; a missing stat reads as the CG default.
    stats: Mapping[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class KitOptionRow:
    """One priced option in a starting kit."""

    report: TechniquePowerReport
    source: OptionSource
    castable: bool
    mostly_estimate: bool
    #: Baseline DE at the catalog panel's last knobs, or None when that corpus is not cached.
    anchor_de: float | None
    in_kit: bool


@dataclass(frozen=True, slots=True)
class StartingKitReport:
    """A character-creation combination priced as the picks a new character gets."""

    params: StartingKitParams
    roller_points: int
    pick_budget: int
    #: Ranked by baseline DE (highest first), then name, then technique id.
    rows: tuple[KitOptionRow, ...]
    kit_baseline_de: float
    kit_formula_de: float
    kit_estimate_de: float
    castable_count: int
    floor: FloorResult


def _kit_options(params: StartingKitParams) -> list[tuple[Technique, OptionSource]]:
    """Character creation's own option set, each option tagged once by its first source."""
    options = cg_catalog.get_technique_options(
        params.path, params.gift, params.tradition, include_unready=True
    )
    species_options = cg_catalog.get_species_technique_options(params.species, include_unready=True)
    sourced: dict[int, tuple[Technique, OptionSource]] = {}
    for technique in options.pool:
        sourced.setdefault(technique.pk, (technique, OptionSource.PATH))
    for technique in options.tradition:
        sourced.setdefault(technique.pk, (technique, OptionSource.TRADITION))
    for technique in species_options:
        sourced.setdefault(technique.pk, (technique, OptionSource.SPECIES))
    return list(sourced.values())


def _cached_anchor_de(anchor_params: TechniqueAnalyticsParams | None) -> dict[int, float]:
    """Baseline DE by technique id from the cached catalog corpus, never evaluating (P8)."""
    if anchor_params is None:
        return {}
    cached = cache.get(_corpus_cache_key(anchor_params))
    if cached is None:
        return {}
    reports, _reference = cached
    return {report.technique_id: report.baseline_de for report in reports}


def build_starting_kit_report(
    params: StartingKitParams,
    *,
    anchor_params: TechniqueAnalyticsParams | None = None,
) -> StartingKitReport:
    """Price one character-creation combination as the picks a new character gets (#3716).

    Options are priced at level 1 and gift thread level 0 with the given stats; the kit
    is the top `1 + extra_picks` options by baseline DE (P1). Options without an action
    template are priced and flagged (P2). Evaluator helpers are called through their
    module objects so tests can patch them at their origin.
    """
    context = EvalContext(
        level=STARTING_LEVEL,
        thread_level=STARTING_THREAD_LEVEL,
        roller_points=starting_stats_roller_points(dict(params.stats)),
        target_difficulty=_TARGET_DIFFICULTY_DEFAULT,
        roll_modifier=_ROLL_MODIFIER_DEFAULT,
    )
    reference = de_valuation.compute_reference_frame(context)
    bands = de_valuation.matchup_bands(context)
    multiplier_cache: dict[int, Decimal] = {}
    priced = [
        (
            technique_power_eval.evaluate_technique(
                technique,
                context,
                reference,
                _multiplier_cache=multiplier_cache,
                _bands=bands,
            ),
            source,
        )
        for technique, source in _kit_options(params)
    ]
    priced.sort(key=lambda pair: (-pair[0].baseline_de, pair[0].name.lower(), pair[0].technique_id))

    pick_budget = 1 + params.extra_picks
    anchors = _cached_anchor_de(anchor_params)
    rows = tuple(
        KitOptionRow(
            report=report,
            source=source,
            castable=is_castable(report),
            mostly_estimate=is_mostly_estimate(report),
            anchor_de=anchors.get(report.technique_id),
            in_kit=index < pick_budget,
        )
        for index, (report, source) in enumerate(priced)
    )
    kit = [row.report for row in rows if row.in_kit]
    return StartingKitReport(
        params=params,
        roller_points=context.roller_points,
        pick_budget=pick_budget,
        rows=rows,
        kit_baseline_de=sum(report.baseline_de for report in kit),
        kit_formula_de=sum(report.formula_baseline_de for report in kit),
        kit_estimate_de=sum(report.estimated_baseline_de for report in kit),
        castable_count=sum(1 for row in rows if row.castable),
        floor=meets_combat_floor(row.report for row in rows),
    )


class PoolScanFilter(StrEnum):
    """Which starting pools the scan lists."""

    FAILS_FLOOR = "fails_floor"
    NOTHING_CASTABLE = "nothing_castable"
    ALL = "all"


DEFAULT_POOL_SCAN_FILTER = PoolScanFilter.FAILS_FLOOR

#: `PathGiftGrant.starter_techniques` through-table column names (Django's auto-through
#: naming: lowercased owning model name + `_id`), named as module constants rather than
#: bare string literals in the `values_list` call below (#3716 Task 3 Step 1).
_THROUGH_GRANT_COLUMN = "pathgiftgrant_id"
_THROUGH_TECHNIQUE_COLUMN = "technique_id"


@dataclass(frozen=True, slots=True)
class PoolScanRow:
    """One path and gift starter pool judged against the combat floor (#3716 P4)."""

    path_id: int
    path_name: str
    gift_id: int
    gift_name: str
    option_count: int
    castable_count: int
    floor: FloorResult
    best_single_de: float


@dataclass(frozen=True, slots=True)
class PoolScanCounts:
    """How many pools each scan filter would list."""

    fails_floor: int
    nothing_castable: int
    all: int


def resolve_pool_scan_filter(value: str) -> PoolScanFilter:
    """Whitelist-or-fallback for a `scan` querystring value."""
    try:
        return PoolScanFilter(value)
    except ValueError:
        return DEFAULT_POOL_SCAN_FILTER


def clear_corpus_cache(params: TechniqueAnalyticsParams) -> None:
    """Drop the cached catalog corpus for *params* so the next build recomputes (P5)."""
    cache.delete(_corpus_cache_key(params))


def _starting_corpus() -> dict[int, TechniquePowerReport]:
    """Every technique priced once at the default starting context, cached by revision.

    Never called by `build_starting_kit_report` - that builder prices only one
    combination's own options at each character's own stats, not the whole catalog.
    """
    default_stats = dict.fromkeys(REQUIRED_STATS, STAT_DEFAULT_VALUE)
    roller_points = starting_stats_roller_points(default_stats)
    key = f"tuning-tech-power-starting-corpus:{technique_catalog_revision()}:{roller_points}"
    cached = cache.get(key)
    if cached is None:
        context = EvalContext(
            level=STARTING_LEVEL,
            thread_level=STARTING_THREAD_LEVEL,
            roller_points=roller_points,
            target_difficulty=_TARGET_DIFFICULTY_DEFAULT,
            roll_modifier=_ROLL_MODIFIER_DEFAULT,
        )
        cached = technique_power_eval.evaluate_all_with_reference(context)
        cache.set(key, cached, _CORPUS_CACHE_TIMEOUT)
    reports, _reference = cached
    return {report.technique_id: report for report in reports}


def build_pool_scan() -> tuple[PoolScanRow, ...]:
    """Judge every path starter pool against the combat floor at the starting context.

    Two queries for the pools (the grants, then the grant-to-technique through rows)
    and one cached catalog evaluation; no per-pool query or evaluation.
    """
    reports = _starting_corpus()
    through = PathGiftGrant.starter_techniques.through
    technique_ids_by_grant: dict[int, list[int]] = {}
    for grant_id, technique_id in through.objects.values_list(
        _THROUGH_GRANT_COLUMN, _THROUGH_TECHNIQUE_COLUMN
    ):
        technique_ids_by_grant.setdefault(grant_id, []).append(technique_id)

    rows: list[PoolScanRow] = []
    grants = PathGiftGrant.objects.select_related("path", "gift").order_by(
        "path__name", "gift__name"
    )
    for grant in grants:
        pool = [reports[pk] for pk in technique_ids_by_grant.get(grant.pk, []) if pk in reports]
        if not pool:
            continue
        rows.append(
            PoolScanRow(
                path_id=grant.path_id,
                path_name=grant.path.name,
                gift_id=grant.gift_id,
                gift_name=grant.gift.name,
                option_count=len(pool),
                castable_count=sum(1 for report in pool if is_castable(report)),
                floor=meets_combat_floor(pool),
                best_single_de=max(report.baseline_de for report in pool),
            )
        )
    return tuple(rows)


def filter_pool_scan(
    rows: Sequence[PoolScanRow], scan_filter: PoolScanFilter
) -> tuple[PoolScanRow, ...]:
    """Pools the chosen filter lists."""
    if scan_filter == PoolScanFilter.FAILS_FLOOR:
        return tuple(row for row in rows if not row.floor.met)
    if scan_filter == PoolScanFilter.NOTHING_CASTABLE:
        return tuple(row for row in rows if row.castable_count == 0)
    return tuple(rows)


def count_pool_scan(rows: Sequence[PoolScanRow]) -> PoolScanCounts:
    """Counts for each filter chip."""
    return PoolScanCounts(
        fails_floor=sum(1 for row in rows if not row.floor.met),
        nothing_castable=sum(1 for row in rows if row.castable_count == 0),
        all=len(rows),
    )
