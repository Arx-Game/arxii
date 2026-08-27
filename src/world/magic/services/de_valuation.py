"""Shared row/technique-independent DE (damage-equivalent) formula core (#3390).

Extracted from ``world.magic.services.technique_power_eval`` (#3279) so the standalone
condition (``condition_power_eval.py``) and capability (``capability_power_eval.py``)
evaluators can price against the EXACT SAME formulas and the exact same self-anchoring
``ReferenceFrame`` the shipped Techniques panel already uses — never a second, drifting
implementation of the same math (#3390's whole point: one currency across three
instruments). ``technique_power_eval.py`` now imports this module for its own
row-independent arithmetic instead of inlining it.

**This refactor is REQUIRED to be byte-identical.** Every function body below is moved
verbatim (only renamed, un-underscored, and generalized in signature where the docstring
says so) from ``technique_power_eval.py``. The existing
``world/magic/tests/test_technique_power_eval_valuators.py`` regression suite — especially
``test_defend_content_parses_to_multiply_half_regression`` and
``test_defend_content_values_as_50_percent_mitigation`` — is the tripwire proving this.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import statistics
from typing import TYPE_CHECKING

from world.magic.types.technique_power import EvalContext, ReferenceFrame

if TYPE_CHECKING:
    from world.conditions.models import ConditionTemplate

#: The synthetic "reference attack" profile used by both the technique generic-modifier
#: valuator and (#3390) the standalone condition/capability valuators to measure how much
#: a roll_modifier shift moves a nominal attack's expected damage. A fixed synthetic
#: profile (rather than any one payload's own numbers) avoids circularity — see
#: :func:`reference_attack_de`.
_MITIGATION_REFERENCE_BASE_DAMAGE = 5
_MITIGATION_REFERENCE_MULTIPLIER = Decimal("1.00")
_MITIGATION_REFERENCE_PER_EXTRA_SL = 2
_MITIGATION_REFERENCE_MIN_SL = 1


@dataclass(frozen=True, slots=True)
class MatchupBand:
    """One outcome's share of the 1-100 roll space (#3279, extracted #3390).

    Local stand-in for ``web.admin.tuning.checks_analytics.OutcomeBand`` — only
    the two fields every evaluator reads (``success_level``, ``probability``).
    """

    success_level: int
    probability: float


def matchup_bands(context: EvalContext) -> list[MatchupBand]:
    """Replicate ``checks_analytics.compute_matchup`` locally (#3279, extracted #3390).

    Derives the roller-minus-target rank difference exactly as
    ``world.checks.services._compute_check_breakdown`` does (a missing rank —
    below every ``CheckRank.min_points`` — contributes 0), selects the nearest
    seeded ``ResultChart`` for that difference, then walks every possible roll
    1..100 applying the same clamp the check engine applies
    (``effective = max(1, min(100, roll + roll_modifier))``) and tallies which
    ``ResultChartOutcome`` row each lands in. Returns ``[]`` when no
    ``ResultChart`` has been seeded at all (no rank difference to fall back to).

    ``world`` code must never import from ``web`` (web depends on world, not the
    reverse) — this is a local, byte-for-byte-equivalent replica of
    ``compute_matchup``'s ~40-line roll enumeration over the same tables, not a
    parallel formula.
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
        MatchupBand(success_level=levels[key], probability=count / 100.0)
        for key, count in counts.items()
    ]


def cached_damage_multiplier(success_level: int, cache: dict[int, Decimal]) -> Decimal:
    """DB-backed ``get_damage_multiplier`` lookup, memoized per evaluation run (#3279).

    ``cache`` is owned by the caller (fresh per evaluator run, or per standalone
    single-entity call) so a staff tuning edit to ``DamageSuccessLevelMultiplier``
    is always picked up by the NEXT run — never stale across runs, only
    de-duplicated within one.
    """
    if success_level not in cache:
        from world.conditions.services import get_damage_multiplier  # noqa: PLC0415

        cache[success_level] = get_damage_multiplier(success_level)
    return cache[success_level]


def reference_attack_de(
    bands: list[MatchupBand],
    *,
    effective_power: int,
    multiplier_cache: dict[int, Decimal],
) -> float:
    """DE of the synthetic nominal reference-attack profile at *bands* (#3279, extracted #3390).

    ``base_damage=5, multiplier=1, per_extra_sl=2, min_sl=1`` — the same
    ``_scale_by_power_and_sl``-shaped formula the damage valuator uses, inlined
    here (rather than a real ``TechniqueDamageProfile`` row) so a generic
    roll_modifier shift's DE impact can be measured without depending on any one
    payload's own (possibly non-attack) numbers. Shared by the technique
    generic-modifier valuator and, as of #3390, the standalone condition and
    capability generic-modifier/check-bridge valuators.
    """
    expected = 0.0
    for band in bands:
        if band.success_level < _MITIGATION_REFERENCE_MIN_SL:
            continue
        budget = (
            _MITIGATION_REFERENCE_BASE_DAMAGE
            + int(_MITIGATION_REFERENCE_MULTIPLIER * effective_power)
            + _MITIGATION_REFERENCE_PER_EXTRA_SL
            * max(0, band.success_level - _MITIGATION_REFERENCE_MIN_SL)
        )
        multiplier = cached_damage_multiplier(band.success_level, multiplier_cache)
        expected += band.probability * float(budget) * float(multiplier)
    return expected


def dot_per_round(
    condition: ConditionTemplate, *, severity: float, stack_count: int = 1
) -> float | None:
    """Per-round DoT throughput for *condition* at *severity* (#3390, extracted from
    ``technique_power_eval._dot_valuation``'s core).

    ``severity`` accepts either a plain authored severity (a standalone condition
    valuation's ``at_severity``) or a cast's band-weighted expected severity (a
    technique valuation's float expectation) — both are the same "how severe" axis,
    just sourced differently by the two callers.

    Queries ``ConditionDamageOverTime.objects.filter(condition=condition)``
    (condition-level rows only — stage-specific DoT rows are not walked, a
    deliberate best-guess simplification inherited unchanged from the original
    technique valuator). Returns ``None`` when the condition carries no such row,
    else ``sum(dot.base_damage * (severity if dot.scales_with_severity else 1) *
    (stack_count if dot.scales_with_stacks else 1) for dot in dot_rows)``.
    """
    from world.conditions.models import ConditionDamageOverTime  # noqa: PLC0415

    dot_rows = list(ConditionDamageOverTime.objects.filter(condition=condition))
    if not dot_rows:
        return None

    return sum(
        dot.base_damage
        * (severity if dot.scales_with_severity else 1)
        * (stack_count if dot.scales_with_stacks else 1)
        for dot in dot_rows
    )


def modifier_effect_shift(condition: ConditionTemplate, *, severity: float) -> float | None:
    """Total non-team-lane ``ConditionModifierEffect`` shift for *condition* at *severity*
    (#3390, extracted from ``technique_power_eval._generic_modifier_valuation``'s per-band
    sum core).

    Queries ``ConditionModifierEffect.objects.filter(condition=condition).exclude(
    modifier_target__name=TEAM_DAMAGE_PERCENT_TARGET_NAME)`` — the team-damage-percent
    lane is priced separately (technique-only; #3390's standalone condition evaluator
    surfaces it as an ``UNPRICEABLE`` gap, see ``condition_power_eval.py``). Returns
    ``None`` when the condition carries no such (non-team-lane) row, else
    ``sum(effect.value * severity if effect.scales_with_severity else effect.value for
    effect in effects)``.
    """
    from world.conditions.models import ConditionModifierEffect  # noqa: PLC0415
    from world.mechanics.constants import TEAM_DAMAGE_PERCENT_TARGET_NAME  # noqa: PLC0415

    effects = list(
        ConditionModifierEffect.objects.filter(condition=condition).exclude(
            modifier_target__name=TEAM_DAMAGE_PERCENT_TARGET_NAME
        )
    )
    if not effects:
        return None

    return sum(
        (effect.value * severity if effect.scales_with_severity else effect.value)
        for effect in effects
    )


def mitigation_value(
    condition: ConditionTemplate, *, duration: float, reference: ReferenceFrame
) -> tuple[float, str] | None:
    """Damage-mitigation DE value for *condition* over *duration* rounds (#3390, extracted
    from ``technique_power_eval._mitigation_valuation``'s core).

    Delegates the flow-step walk to
    ``world.magic.services.targeting.protective_magnitude``. ``multiply`` mode:
    ``(1 - factor) * reference.incoming_dpr * duration``. ``flat`` mode: ``amount *
    duration``, capped at ``reference.incoming_dpr * duration`` (a flat reduction can't
    logically mitigate more than the reference hit itself would have dealt). Returns
    ``None`` when the condition's protective family (if any) isn't a recognized
    MODIFY_PAYLOAD shape — the caller falls back to UNPRICEABLE. Returns
    ``(value, detail_string)`` so callers build their own labeled ``PayloadValuation``.
    """
    from world.magic.services import targeting  # noqa: PLC0415

    magnitude = targeting.protective_magnitude(condition)
    if magnitude is None:
        return None

    if magnitude.mode == targeting.PROTECTIVE_MAGNITUDE_MULTIPLY:
        value = (1 - magnitude.factor) * reference.incoming_dpr * duration
        detail = f"(1 - {magnitude.factor}) x incoming_dpr x {duration:.2f} expected rounds"
    else:
        cap = reference.incoming_dpr * duration
        raw = magnitude.amount * duration
        value = min(raw, cap) if cap > 0 else raw
        detail = f"{magnitude.amount} x {duration:.2f} expected rounds, capped at {cap:.2f}"

    return value, detail


def is_team_lane_condition(condition: ConditionTemplate) -> bool:
    """True if *condition* rides the bounded team-damage-percent lane (#2643, extracted
    #3390 from ``technique_power_eval._is_team_lane_condition``).

    A condition whose template carries a ``ConditionModifierEffect(
    modifier_target__name="team_damage_percent", scales_with_severity=True)`` row prices
    its severity via ``priced_percent_severity`` instead of its own authored formula —
    that lane needs a ``target_kind`` (ALLY vs ENEMY) to sign correctly, which only
    exists once a condition is wrapped in a technique's ``TechniqueAppliedCondition``
    row (#3390's standalone condition evaluator has no such context — see Decision 6 in
    issue #3390).
    """
    from world.conditions.models import ConditionModifierEffect  # noqa: PLC0415
    from world.mechanics.constants import TEAM_DAMAGE_PERCENT_TARGET_NAME  # noqa: PLC0415

    return ConditionModifierEffect.objects.filter(
        condition=condition,
        modifier_target__name=TEAM_DAMAGE_PERCENT_TARGET_NAME,
        scales_with_severity=True,
    ).exists()


def has_stage_scoped_dot(condition: ConditionTemplate) -> bool:
    """True if *condition* carries any stage-scoped ``ConditionDamageOverTime`` row (#3390).

    :func:`dot_per_round` only reads condition-level DoT rows (matching
    ``technique_power_eval._dot_valuation``'s own pre-existing scope) — a stage-specific
    DoT row is invisible to it. The standalone condition evaluator surfaces that gap as a
    named ``UNPRICEABLE`` row rather than silently under-pricing (Decision 6 in #3390).
    """
    from world.conditions.models import ConditionDamageOverTime  # noqa: PLC0415

    return ConditionDamageOverTime.objects.filter(stage__condition=condition).exists()


def compute_reference_frame(context: EvalContext) -> ReferenceFrame:
    """Self-anchoring reference DPR for one evaluation run (#3279, extracted #3390).

    Median baseline attack DE across every technique carrying at least one damage-profile
    row, at *context* — the same self-anchoring bootstrap
    ``technique_power_eval.evaluate_all_with_reference``'s pass 1 always computed, now
    extracted as its own public function (Decision 2 in #3390) so the standalone
    condition and capability evaluators share the EXACT same reference computation and
    cache key rather than re-deriving a second median — "1 DE" means the same thing
    everywhere. ``technique_power_eval.evaluate_all_with_reference`` is now a thin
    wrapper: call this, then its own pass 2 as before.

    Deferred import of ``technique_power_eval`` (rather than a module-level import)
    because that module imports THIS one at module level for its own delegated
    formulas — a module-level import here would be circular.
    """
    from world.magic.models.techniques import Technique  # noqa: PLC0415
    from world.magic.services import technique_power_eval  # noqa: PLC0415

    multiplier_cache: dict[int, Decimal] = {}
    bands = matchup_bands(context)

    attack_techniques = (
        Technique.objects.filter(damage_profiles__isnull=False)
        .distinct()
        .select_related("gift", "effect_type")
    )
    placeholder_reference = ReferenceFrame(
        outgoing_dpr=0.0, incoming_dpr=0.0, source_label="pending"
    )
    baseline_des = [
        technique_power_eval.evaluate_technique(
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
        return ReferenceFrame(
            outgoing_dpr=median, incoming_dpr=median, source_label="median-attack estimate"
        )
    return ReferenceFrame(outgoing_dpr=0.0, incoming_dpr=0.0, source_label="no attack techniques")
