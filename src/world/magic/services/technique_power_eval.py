"""Technique combat-power evaluator (#3279).

Prices every authored technique's combat payloads into DE (damage-equivalent per
cast in a reference matchup) and compares its baseline power (``technique.intensity``
alone) to an "amplified" anchor (a caster with a fully-matched engaged covenant
role/specialty at the panel's thread level). Drives the Game Tuning "Techniques"
panel (a later task); this module has no view/admin dependency of its own.

Only the damage payload valuator is implemented here (Task 1 of #3279's plan,
``docs/plans/3279-technique-power-eval-plan.md``) — buffs, debuffs, control,
mitigation, heals, dispel, and capability grants all return an empty valuation
list for now and are picked up by the follow-on task. Power/anima plumbing (the
baseline-vs-amplified power comparison, effective anima cost, windup division) is
complete in this task.

**Layering note:** the currency spec calls for
``web.admin.tuning.checks_analytics.compute_matchup`` to derive the per-cast
success-level distribution. ``world`` code must never import from ``web`` (web
depends on world, not the reverse — no other `world` *service* module does this;
the handful of existing `world -> web` imports are all thin view/admin-layer
plumbing, not business logic). ``compute_matchup`` itself is pure Django ORM over
``world.traits`` models with no web dependency of its own, so ``_matchup_bands``
below is a local, byte-for-byte-equivalent replica of its ~40-line roll
enumeration over the same tables — see that function's docstring.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import statistics
from typing import TYPE_CHECKING

from world.magic.models.techniques import Technique
from world.magic.services.power_terms import (
    blend_power_contribution,
    get_covenant_role_blend_config,
    specialty_power_contribution,
)
from world.magic.types.technique_power import (
    EvalContext,
    PayloadValuation,
    ReferenceFrame,
    TechniquePowerReport,
    ValuationProvenance,
)

if TYPE_CHECKING:
    from world.magic.models.techniques import AbstractDamageProfile

#: A caster whose sole engaged role is a fully-matched anchor (blend_weight=1.0,
#: specialty multiplier_tenths=10 => x1.0) — the amplified-power comparison point.
_ANCHOR_BLEND_WEIGHT = Decimal(1)
_ANCHOR_SPECIALTY_MULTIPLIER_TENTHS = 10

#: current_anima passed to calculate_effective_anima_cost — large enough that no
#: technique in the catalog could ever hit the ``lethal`` overburn floor, so the
#: figure returned is always the pure delta-formula cost, never a deficit-clamped one.
_ANIMA_HEADROOM = 1_000_000


@dataclass(frozen=True, slots=True)
class _MatchupBand:
    """One outcome's share of the 1-100 roll space (#3279).

    Local stand-in for ``web.admin.tuning.checks_analytics.OutcomeBand`` — only
    the two fields this evaluator reads (``success_level``, ``probability``).
    """

    success_level: int
    probability: float


def _matchup_bands(context: EvalContext) -> list[_MatchupBand]:
    """Replicate ``checks_analytics.compute_matchup`` locally (see module docstring).

    Derives the roller-minus-target rank difference exactly as
    ``world.checks.services._compute_check_breakdown`` does (a missing rank —
    below every ``CheckRank.min_points`` — contributes 0), selects the nearest
    seeded ``ResultChart`` for that difference, then walks every possible roll
    1..100 applying the same clamp the check engine applies
    (``effective = max(1, min(100, roll + roll_modifier))``) and tallies which
    ``ResultChartOutcome`` row each lands in. Returns ``[]`` when no
    ``ResultChart`` has been seeded at all (no rank difference to fall back to).
    """
    from world.traits.models import CheckRank, ResultChart, ResultChartOutcome  # noqa: PLC0415

    roller_rank = CheckRank.get_rank_for_points(context.roller_points)
    target_rank = CheckRank.get_rank_for_points(context.target_difficulty)
    rank_difference = (roller_rank.rank if roller_rank else 0) - (
        target_rank.rank if target_rank else 0
    )

    chart = ResultChart.get_chart_for_difference(rank_difference)
    if chart is None:
        return []

    outcome_rows = list(
        ResultChartOutcome.objects.filter(chart=chart)
        .select_related("outcome")
        .order_by("min_roll")
    )

    counts: dict[int, int] = {}
    levels: dict[int, int] = {}
    for roll in range(1, 101):
        effective = max(1, min(100, roll + context.roll_modifier))
        matched = next(
            (row for row in outcome_rows if row.min_roll <= effective <= row.max_roll),
            None,
        )
        if matched is None:
            continue
        key = matched.outcome_id
        counts[key] = counts.get(key, 0) + 1
        levels[key] = matched.outcome.success_level

    return [
        _MatchupBand(success_level=levels[key], probability=count / 100.0)
        for key, count in counts.items()
    ]


def _amplified_power_delta(context: EvalContext) -> int:
    """Power gained going from baseline to the "fully matched anchor" (#3279).

    Sums the two role-band pure helpers (extracted from ``power_terms.py`` in
    this same task) at ``context.thread_level``, each int-truncated separately
    before summing — mirroring how ``_derive_power``'s TERM stage truncates
    every provider's contribution independently before adding it to the
    ledger total.
    """
    config = get_covenant_role_blend_config()
    blend = int(
        blend_power_contribution(
            context.thread_level, _ANCHOR_BLEND_WEIGHT, config.multiplier_tenths
        )
    )
    specialty = int(
        specialty_power_contribution(context.thread_level, _ANCHOR_SPECIALTY_MULTIPLIER_TENTHS)
    )
    return blend + specialty


def _cached_damage_multiplier(success_level: int, cache: dict[int, Decimal]) -> Decimal:
    """DB-backed ``get_damage_multiplier`` lookup, memoized per evaluation run.

    ``cache`` is owned by the caller (fresh per ``evaluate_all`` run, or per
    standalone ``evaluate_technique`` call) so a staff tuning edit to
    ``DamageSuccessLevelMultiplier`` is always picked up by the NEXT run —
    never stale across runs, only de-duplicated within one.
    """
    if success_level not in cache:
        from world.conditions.services import get_damage_multiplier  # noqa: PLC0415

        cache[success_level] = get_damage_multiplier(success_level)
    return cache[success_level]


def _damage_row_valuation(
    row: AbstractDamageProfile,
    *,
    power: int,
    bands: list[_MatchupBand],
    multiplier_cache: dict[int, Decimal],
) -> PayloadValuation:
    """Expected DE for one ``TechniqueDamageProfile`` row at a given power.

    ``expected = Σ over bands with sl >= row.minimum_success_level of
    P(sl) x row.compute_damage_budget(power, sl) x get_damage_multiplier(sl)``
    — the currency spec's attack formula.
    """
    expected = 0.0
    for band in bands:
        if band.success_level < row.minimum_success_level:
            continue
        budget = row.compute_damage_budget(effective_power=power, success_level=band.success_level)
        multiplier = _cached_damage_multiplier(band.success_level, multiplier_cache)
        expected += band.probability * float(budget) * float(multiplier)

    label = row.damage_type.name if row.damage_type_id else "untyped damage"
    return PayloadValuation(
        kind="damage",
        label=label,
        value=expected,
        provenance=ValuationProvenance.FORMULA,
        detail=f"E[budget x mult] over SL bands = {expected:.2f}",
    )


def _damage_valuations(
    technique: Technique,
    *,
    power: int,
    bands: list[_MatchupBand],
    multiplier_cache: dict[int, Decimal],
) -> list[PayloadValuation]:
    """One ``PayloadValuation`` per damage-profile row, at the given power."""
    return [
        _damage_row_valuation(row, power=power, bands=bands, multiplier_cache=multiplier_cache)
        for row in technique.cached_damage_profiles
    ]


def _effective_anima(technique: Technique) -> int:
    """Effective anima cost at the technique's own (unmodified) intensity/control."""
    from world.magic.services.techniques import calculate_effective_anima_cost  # noqa: PLC0415

    result = calculate_effective_anima_cost(
        base_cost=technique.anima_cost,
        runtime_intensity=technique.intensity,
        runtime_control=technique.control,
        current_anima=_ANIMA_HEADROOM,
        lethal=True,
    )
    return result.effective_cost


def evaluate_technique(
    technique: Technique,
    context: EvalContext,
    reference: ReferenceFrame,  # noqa: ARG001 — reserved for Task 2's buff/mitigation/dispel
    # valuators, which value against reference.outgoing_dpr/incoming_dpr; the damage
    # valuator built in this task doesn't need it.
    *,
    _multiplier_cache: dict[int, Decimal] | None = None,
    _bands: list[_MatchupBand] | None = None,
) -> TechniquePowerReport:
    """Full combat-power report for one technique at one evaluation context (#3279).

    Baseline power is ``technique.intensity`` alone — the same figure
    ``_derive_power(character=None)`` returns
    (``world/magic/services/techniques.py:394``, ``PowerLedgerBuilder(base=max(0,
    channeled_intensity)).build()`` when there is no character to derive
    contributions from). Amplified power adds ``_amplified_power_delta`` on top —
    the "fully matched anchor" comparison point.

    ``_multiplier_cache``/``_bands`` let ``evaluate_all`` share one damage-
    multiplier cache and one matchup-band computation across every technique in
    a run; a standalone caller computes its own (fresh per call) when omitted.
    """
    if _multiplier_cache is None:
        _multiplier_cache = {}
    if _bands is None:
        _bands = _matchup_bands(context)

    baseline_power = technique.intensity
    amplified_power = baseline_power + _amplified_power_delta(context)
    effective_anima = _effective_anima(technique)

    if not _bands:
        return TechniquePowerReport(
            technique_id=technique.pk,
            name=technique.name,
            gift_name=technique.gift.name,
            level=technique.level,
            tier=technique.tier,
            category=technique.effect_type.category,
            baseline_power=baseline_power,
            amplified_power=amplified_power,
            baseline_de=0.0,
            amplified_de=0.0,
            valuations=(),
            effective_anima=effective_anima,
            de_per_anima=0.0,
            flags=("no_result_charts",),
        )

    valuations = _damage_valuations(
        technique, power=baseline_power, bands=_bands, multiplier_cache=_multiplier_cache
    )
    amplified_valuations = _damage_valuations(
        technique, power=amplified_power, bands=_bands, multiplier_cache=_multiplier_cache
    )
    baseline_de = sum(v.value for v in valuations)
    amplified_de = sum(v.value for v in amplified_valuations)

    flags: list[str] = []
    damage_profiles = technique.cached_damage_profiles
    if any(row.uses_equipped_weapon for row in damage_profiles):
        flags.append("weapon_scaled")
    if any(row.execute_missing_health_multiplier for row in damage_profiles):
        flags.append("execute_ramp")

    if technique.windup_rounds > 0:
        divisor = 1 + technique.windup_rounds
        baseline_de /= divisor
        amplified_de /= divisor
        flags.append(f"windup:{technique.windup_rounds}")

    de_per_anima = baseline_de / max(1, effective_anima)

    return TechniquePowerReport(
        technique_id=technique.pk,
        name=technique.name,
        gift_name=technique.gift.name,
        level=technique.level,
        tier=technique.tier,
        category=technique.effect_type.category,
        baseline_power=baseline_power,
        amplified_power=amplified_power,
        baseline_de=baseline_de,
        amplified_de=amplified_de,
        valuations=tuple(valuations),
        effective_anima=effective_anima,
        de_per_anima=de_per_anima,
        flags=tuple(flags),
    )


def evaluate_all(context: EvalContext) -> list[TechniquePowerReport]:
    """Evaluate every technique in the catalog, two-pass (#3279).

    Pass 1 computes baseline attack DE for every technique carrying at least one
    damage-profile row; the median of those figures becomes the reference frame's
    ``outgoing_dpr``/``incoming_dpr`` (self-anchoring — derived from the game's own
    content, not an authored constant). Pass 2 evaluates every technique in the
    catalog against that reference. A run shares one matchup-band computation and
    one damage-multiplier cache across both passes and every technique.
    """
    multiplier_cache: dict[int, Decimal] = {}
    bands = _matchup_bands(context)

    attack_techniques = (
        Technique.objects.filter(damage_profiles__isnull=False)
        .distinct()
        .select_related("gift", "effect_type")
    )
    placeholder_reference = ReferenceFrame(
        outgoing_dpr=0.0, incoming_dpr=0.0, source_label="pending"
    )
    baseline_des = [
        evaluate_technique(
            technique,
            context,
            placeholder_reference,
            _multiplier_cache=multiplier_cache,
            _bands=bands,
        ).baseline_de
        for technique in attack_techniques
    ]

    if baseline_des:
        median = statistics.median(baseline_des)
        reference = ReferenceFrame(
            outgoing_dpr=median,
            incoming_dpr=median,
            source_label="median-attack estimate",
        )
    else:
        reference = ReferenceFrame(
            outgoing_dpr=0.0, incoming_dpr=0.0, source_label="no attack techniques"
        )

    all_techniques = Technique.objects.all().select_related("gift", "effect_type")
    return [
        evaluate_technique(
            technique, context, reference, _multiplier_cache=multiplier_cache, _bands=bands
        )
        for technique in all_techniques
    ]
