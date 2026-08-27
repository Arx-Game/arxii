"""Technique combat-power evaluator (#3279).

Prices every authored technique's combat payloads into DE (damage-equivalent per
cast in a reference matchup) and compares its baseline power (``technique.intensity``
alone) to an "amplified" anchor (a caster with a fully-matched engaged covenant
role/specialty at the panel's thread level). Drives the Game Tuning "Techniques"
panel (a later task); this module has no view/admin dependency of its own.

Task 1 built the damage payload valuator, the power/anima plumbing (baseline-vs-
amplified power comparison, effective anima cost, windup division), and the
two-pass reference-DPR bootstrap. Task 2 (this module, still) adds every other
payload valuator: ALLY/SELF applied-condition buffs (the bounded team-damage-
percent lane plus a generic roll-modifier-shift estimate for other
``ConditionModifierEffect``-carrying conditions), ENEMY applied-condition
debuffs (damage-over-time, the same generic modifier-shift estimate, and a
technique-level hard-control estimate for HOLD/FEAR/DISTRACTION function
tags), a mitigation valuator that PARSES a protective condition's reactive-
trigger flow steps (see ``world.magic.services.targeting.protective_magnitude``)
rather than probing empirically, treatment heals, an unpriced dispel flag, and
an explicitly-zero INERT_PAYLOAD row per capability grant (no cast seam exists
for technique capability grants — see this app's CLAUDE.md).

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

from decimal import Decimal
from typing import TYPE_CHECKING

from world.magic.constants import (
    PCT_PER_POWER_TENTHS,
    TEAM_BUFF_LANE_CAP_PERCENT,
    TechniqueFunction,
)
from world.magic.models.techniques import ConditionTargetKind, Technique
from world.magic.services import de_valuation
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
    from world.magic.models.techniques import (
        AbstractAppliedCondition,
        AbstractDamageProfile,
        TechniqueTreatment,
    )

#: A caster whose sole engaged role is a fully-matched anchor (blend_weight=1.0,
#: specialty multiplier_tenths=10 => x1.0) — the amplified-power comparison point.
_ANCHOR_BLEND_WEIGHT = Decimal(1)
_ANCHOR_SPECIALTY_MULTIPLIER_TENTHS = 10

#: current_anima passed to calculate_effective_anima_cost — large enough that no
#: technique in the catalog could ever hit the ``lethal`` overburn floor, so the
#: figure returned is always the pure delta-formula cost, never a deficit-clamped one.
_ANIMA_HEADROOM = 1_000_000

#: TechniqueFunction tags that a "hard control" valuation (#3279 Task 2) is priced
#: for — a technique landing any of these on an ENEMY-targeted applied condition is
#: valued as locking the target down for the condition's expected duration.
_HARD_CONTROL_FUNCTIONS = frozenset(
    {TechniqueFunction.HOLD, TechniqueFunction.FEAR, TechniqueFunction.DISTRACTION}
)

#: The synthetic reference-attack profile constants that back ``_reference_attack_de``
#: now live in ``de_valuation.py`` (#3390) — see the alias block below.


#: Aliases onto the shared core (#3390) — ``de_valuation.py`` now owns these bodies
#: verbatim; kept under the pre-#3390 private names here so every existing call site
#: in this module (and every existing test importing this module) stays byte-identical.
_MatchupBand = de_valuation.MatchupBand
_matchup_bands = de_valuation.matchup_bands
_reference_attack_de = de_valuation.reference_attack_de
_cached_damage_multiplier = de_valuation.cached_damage_multiplier


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


def _expected_duration_rounds(
    row: AbstractAppliedCondition,
    *,
    power: int,
    bands: list[_MatchupBand],
) -> float:
    """Band-weighted expected duration (rounds) for an applied-condition row.

    Mirrors the damage valuator's SL-band expectation: sums ``P(sl) *
    row.compute_duration_rounds(power, sl)`` over bands with
    ``sl >= row.minimum_success_level``. ``compute_duration_rounds`` can return
    ``None`` (only when a condition template's ``default_duration_value`` is
    itself null); treated as 0 rounds.
    """
    total = 0.0
    for band in bands:
        if band.success_level < row.minimum_success_level:
            continue
        duration = row.compute_duration_rounds(
            effective_power=power, success_level=band.success_level
        )
        total += band.probability * (duration or 0)
    return total


def _expected_severity(
    row: AbstractAppliedCondition,
    *,
    power: int,
    bands: list[_MatchupBand],
) -> float:
    """Band-weighted expected severity for an applied-condition row (mirrors duration)."""
    total = 0.0
    for band in bands:
        if band.success_level < row.minimum_success_level:
            continue
        total += band.probability * row.compute_severity(
            effective_power=power, success_level=band.success_level
        )
    return total


#: Alias onto the shared core (#3390) — see ``de_valuation.is_team_lane_condition``.
_is_team_lane_condition = de_valuation.is_team_lane_condition


def _team_lane_percent(power: int, context: EvalContext) -> int:
    """Local replica of ``world.conditions.services.priced_percent_severity`` (#3279).

    That function resolves its ``target_level`` by looking up a real ``ObjectDB``
    (a ``CharacterSheet`` or ``CombatOpponent``) — this evaluator has no concrete
    target, so it substitutes ``context.level`` for ``target_level`` directly, per
    the currency spec. Same clamp: ``max(1, min(TEAM_BUFF_LANE_CAP_PERCENT, ...))``.
    """
    raw = power * PCT_PER_POWER_TENTHS / 10 / max(1, context.level)
    return max(1, min(TEAM_BUFF_LANE_CAP_PERCENT, round(raw)))


def _team_lane_valuation(
    row: AbstractAppliedCondition,
    *,
    power: int,
    context: EvalContext,
    duration: float,
    reference: ReferenceFrame,
) -> PayloadValuation:
    """Value a team-damage-percent-lane applied-condition row (#3279 Task 2).

    ALLY/SELF: a team-wide damage buff, priced against ``reference.outgoing_dpr``.
    ENEMY: the same bounded lane debuffing the target's own output, priced against
    ``reference.incoming_dpr`` (damage the caster prevents by landing it).
    """
    percent = _team_lane_percent(power, context)
    is_enemy = row.target_kind == ConditionTargetKind.ENEMY
    dpr = reference.incoming_dpr if is_enemy else reference.outgoing_dpr
    value = (percent / 100.0) * dpr * duration
    return PayloadValuation(
        kind="debuff" if is_enemy else "buff",
        label=row.condition.name,
        value=value,
        provenance=ValuationProvenance.FORMULA,
        detail=f"team_damage_percent {percent}% x dpr x {duration:.2f} expected rounds",
    )


def _generic_modifier_valuation(  # noqa: PLR0913 - cohesive per-row valuation params
    row: AbstractAppliedCondition,
    *,
    power: int,
    bands: list[_MatchupBand],
    context: EvalContext,
    duration: float,
    multiplier_cache: dict[int, Decimal],
) -> PayloadValuation | None:
    """Value a non-team-lane, ``ConditionModifierEffect``-carrying applied-condition row.

    Estimates the row's expected roll_modifier shift (severity-weighted, banded)
    then measures its DE impact on the synthetic reference attack
    (:func:`_reference_attack_de`) by re-running the matchup with ``roll_modifier``
    shifted. ALLY/SELF: the shift is assumed to buff the caster's own attack
    (``shifted - base``). ENEMY: the shift is assumed to debuff the target's
    attack against the caster, so the value is the DAMAGE PREVENTED
    (``base - shifted``) — a sign flip from the buff case, per the currency spec.

    Returns ``None`` when *row*'s condition carries no (non-team-lane)
    ``ConditionModifierEffect`` row — the caller falls through to the mitigation
    parse (SELF/ALLY) or leaves the row for the caller's own fallback (ENEMY).

    The row-independent per-severity shift arithmetic is
    ``de_valuation.modifier_effect_shift`` (#3390); an upfront probe call detects
    "no qualifying effects at all" (independent of which bands happen to clear
    ``row.minimum_success_level``) so a condition with effects but only
    below-minimum bands still prices at shift=0 rather than falling through, matching
    pre-#3390 behavior exactly.
    """
    if de_valuation.modifier_effect_shift(row.condition, severity=0) is None:
        return None

    expected_shift = 0.0
    for band in bands:
        if band.success_level < row.minimum_success_level:
            continue
        severity = row.compute_severity(effective_power=power, success_level=band.success_level)
        shift = de_valuation.modifier_effect_shift(row.condition, severity=severity)
        expected_shift += band.probability * (shift or 0.0)

    shifted_roll_modifier = context.roll_modifier + round(expected_shift)
    shifted_context = EvalContext(
        level=context.level,
        thread_level=context.thread_level,
        roller_points=context.roller_points,
        target_difficulty=context.target_difficulty,
        roll_modifier=shifted_roll_modifier,
        passive=context.passive,
    )
    shifted_bands = _matchup_bands(shifted_context)
    base_de = _reference_attack_de(
        bands, effective_power=context.level, multiplier_cache=multiplier_cache
    )
    shifted_de = _reference_attack_de(
        shifted_bands, effective_power=context.level, multiplier_cache=multiplier_cache
    )

    is_enemy = row.target_kind == ConditionTargetKind.ENEMY
    if is_enemy:
        value = (base_de - shifted_de) * duration
        kind = "debuff"
    else:
        value = (shifted_de - base_de) * duration
        kind = "buff" if expected_shift >= 0 else "debuff"

    return PayloadValuation(
        kind=kind,
        label=row.condition.name,
        value=value,
        provenance=ValuationProvenance.ESTIMATE,
        detail=(
            f"E[roll_modifier shift]={expected_shift:.2f} -> DE delta "
            f"{shifted_de - base_de:.2f} x {duration:.2f} expected rounds"
        ),
    )


def _dot_valuation(
    row: AbstractAppliedCondition,
    *,
    power: int,
    bands: list[_MatchupBand],
    duration: float,
) -> PayloadValuation | None:
    """Value an ENEMY applied-condition row whose condition carries damage-over-time.

    ``dot_per_round`` mirrors ``web.admin.tuning.condition_analytics
    .compute_condition_danger``'s own formula: ``base_damage * (severity if
    scales_with_severity else 1) * (row.stack_count if scales_with_stacks else 1)``,
    summed over every ``ConditionDamageOverTime`` row attached directly to the
    condition template (stage-specific DoT rows are not walked — a deliberate
    best-guess simplification; most authored DoT lives at the condition level).
    Returns ``None`` when the condition carries no such row.

    Row-independent arithmetic delegates to ``de_valuation.dot_per_round`` (#3390).
    """
    expected_severity = _expected_severity(row, power=power, bands=bands)
    per_round = de_valuation.dot_per_round(
        row.condition, severity=expected_severity, stack_count=row.stack_count
    )
    if per_round is None:
        return None

    value = per_round * duration
    return PayloadValuation(
        kind="debuff",
        label=row.condition.name,
        value=value,
        provenance=ValuationProvenance.FORMULA,
        detail=f"dot_per_round={per_round:.2f} x {duration:.2f} expected rounds",
    )


def _mitigation_valuation(
    row: AbstractAppliedCondition,
    *,
    duration: float,
    reference: ReferenceFrame,
) -> PayloadValuation | None:
    """Value a SELF/ALLY applied-condition row via the protective-magnitude PARSE.

    Delegates the flow-step walk to
    ``world.magic.services.targeting.protective_magnitude``. ``multiply`` mode:
    ``(1 - factor) * reference.incoming_dpr * duration``. ``flat`` mode:
    ``amount * duration``, capped at ``reference.incoming_dpr * duration`` (a flat
    reduction can't logically mitigate more than the reference hit itself would
    have dealt). Returns ``None`` when the condition's protective family (if any)
    isn't a recognized MODIFY_PAYLOAD shape — the caller falls back to UNPRICEABLE.

    Row-independent arithmetic delegates to ``de_valuation.mitigation_value`` (#3390) —
    THE regression tripwire: ``test_defend_content_parses_to_multiply_half_regression``
    and ``test_defend_content_values_as_50_percent_mitigation`` must still pass
    byte-identically after this delegation.
    """
    result = de_valuation.mitigation_value(row.condition, duration=duration, reference=reference)
    if result is None:
        return None
    value, detail = result

    return PayloadValuation(
        kind="mitigation",
        label=row.condition.name,
        value=value,
        provenance=ValuationProvenance.PARSED,
        detail=detail,
    )


def _unpriceable_valuation(*, label: str, kind: str) -> PayloadValuation:
    """An authoring-gap bucket row: the payload's mechanism could not be classified."""
    return PayloadValuation(
        kind=kind,
        label=label,
        value=0.0,
        provenance=ValuationProvenance.UNPRICEABLE,
        detail="unrecognized payload shape",
    )


def _routed_condition_valuation(  # noqa: PLR0913 - cohesive per-row valuation params
    row: AbstractAppliedCondition,
    *,
    is_enemy: bool,
    power: int,
    bands: list[_MatchupBand],
    context: EvalContext,
    duration: float,
    reference: ReferenceFrame,
    multiplier_cache: dict[int, Decimal],
) -> PayloadValuation:
    """Route one ``TechniqueAppliedCondition`` row to its valuator (#3279 Task 2).

    Per-row routing (see module docstring + ``docs/plans/3279-technique-power-eval-
    plan.md``):

    - Team-damage-percent lane (any target_kind) -> :func:`_team_lane_valuation`.
    - ENEMY + damage-over-time -> :func:`_dot_valuation`.
    - Non-team-lane ``ConditionModifierEffect`` (any target_kind) ->
      :func:`_generic_modifier_valuation`.
    - SELF/ALLY with none of the above -> :func:`_mitigation_valuation`, else
      UNPRICEABLE.
    - ENEMY with none of the above -> UNPRICEABLE.
    """
    if _is_team_lane_condition(row.condition):
        return _team_lane_valuation(
            row, power=power, context=context, duration=duration, reference=reference
        )

    if is_enemy:
        dot = _dot_valuation(row, power=power, bands=bands, duration=duration)
        if dot is not None:
            return dot

    modifier = _generic_modifier_valuation(
        row,
        power=power,
        bands=bands,
        context=context,
        duration=duration,
        multiplier_cache=multiplier_cache,
    )
    if modifier is not None:
        return modifier

    if not is_enemy:
        mitigation = _mitigation_valuation(row, duration=duration, reference=reference)
        if mitigation is not None:
            return mitigation

    return _unpriceable_valuation(
        label=row.condition.name, kind="mitigation" if not is_enemy else "debuff"
    )


def _hard_control_valuation(
    technique: Technique, *, enemy_durations: list[float], reference: ReferenceFrame
) -> PayloadValuation | None:
    """One technique-level "hard control" row, or ``None`` (#3279 Task 2).

    Appended when the technique carries a HOLD/FEAR/DISTRACTION function tag AND
    at least one ENEMY applied-condition row exists — valued at the longest
    expected duration among the technique's ENEMY rows times
    ``reference.incoming_dpr`` (#3279's currency spec; deliberately per-technique,
    not per-row).
    """
    has_hard_control_tag = any(
        tag.function in _HARD_CONTROL_FUNCTIONS for tag in technique.cached_function_tags
    )
    if not has_hard_control_tag or not enemy_durations:
        return None

    control_duration = max(enemy_durations)
    value = control_duration * reference.incoming_dpr
    return PayloadValuation(
        kind="control",
        label="hard control",
        value=value,
        provenance=ValuationProvenance.ESTIMATE,
        detail=f"{control_duration:.2f} expected rounds x incoming_dpr (HOLD/FEAR/DISTRACTION)",
    )


def _condition_application_valuations(  # noqa: PLR0913 - cohesive per-technique valuation params
    technique: Technique,
    *,
    power: int,
    bands: list[_MatchupBand],
    context: EvalContext,
    reference: ReferenceFrame,
    multiplier_cache: dict[int, Decimal],
) -> list[PayloadValuation]:
    """Value every ``TechniqueAppliedCondition`` row plus the technique-level control
    estimate (#3279 Task 2).

    Per-row routing lives in :func:`_routed_condition_valuation`; the technique-level
    hard-control row lives in :func:`_hard_control_valuation`.
    """
    valuations: list[PayloadValuation] = []
    enemy_durations: list[float] = []

    for row in technique.cached_condition_applications:
        duration = _expected_duration_rounds(row, power=power, bands=bands)
        is_enemy = row.target_kind == ConditionTargetKind.ENEMY
        if is_enemy:
            enemy_durations.append(duration)

        valuations.append(
            _routed_condition_valuation(
                row,
                is_enemy=is_enemy,
                power=power,
                bands=bands,
                context=context,
                duration=duration,
                reference=reference,
                multiplier_cache=multiplier_cache,
            )
        )

    control = _hard_control_valuation(
        technique, enemy_durations=enemy_durations, reference=reference
    )
    if control is not None:
        valuations.append(control)

    return valuations


def _treatment_valuations(
    technique: Technique,
    *,
    bands: list[_MatchupBand],
    reference: ReferenceFrame,
) -> list[PayloadValuation]:
    """Value every ``TechniqueTreatment`` row (#3279 Task 2).

    ``TechniqueTreatment`` carries no SL-scaling columns of its own — the healed
    amount lives on its ``TreatmentTemplate`` as three outcome-tier flat amounts
    (``mend_on_crit``/``mend_on_success``/``mend_on_partial``, keyed to the
    treatment's own internal check outcome, not this evaluator's cast SL bands).
    Best-guess mapping (documented deliberately, not hidden): reuse the cast's own
    SL bands and rank each band's success_level against the treatment's own tiers
    (``>= 3`` -> crit, ``== 2`` -> success, ``== 1`` -> partial) — bands below
    ``row.minimum_success_level`` are skipped, same SL gate the damage valuator uses.
    Capped at ``reference.incoming_dpr`` — ``TechniqueTreatment`` has no duration
    field of its own (a heal is instant, not a rounds-long window), so the
    currency spec's ``max(1, expected_duration_rounds if it has one else 1)``
    window is always 1 here.
    """
    rows: list[TechniqueTreatment] = list(technique.treatments.select_related("treatment_template"))
    valuations: list[PayloadValuation] = []
    for row in rows:
        template = row.treatment_template
        expected = 0.0
        for band in bands:
            if band.success_level < row.minimum_success_level:
                continue
            if band.success_level >= 3:  # noqa: PLR2004 - treatment outcome-tier threshold
                mend = template.mend_on_crit
            elif band.success_level == 2:  # noqa: PLR2004 - treatment outcome-tier threshold
                mend = template.mend_on_success
            else:
                mend = template.mend_on_partial
            expected += band.probability * mend

        cap = reference.incoming_dpr
        value = min(expected, cap) if cap > 0 else expected
        valuations.append(
            PayloadValuation(
                kind="heal",
                label=template.name,
                value=value,
                provenance=ValuationProvenance.FORMULA,
                detail=f"E[heal]={expected:.2f}, capped at incoming_dpr={cap:.2f}",
            )
        )
    return valuations


def _dispel_valuation(technique: Technique) -> PayloadValuation | None:
    """One technique-level dispel row (#3279 Task 2) — never priced (v1).

    ``TechniqueRemovedCondition`` payloads are deliberately not valued: dispel's
    combat impact depends entirely on what the target happened to have applied,
    which this evaluator has no visibility into. One row per technique (not per
    removed-condition row), value 0, naming every condition the technique removes.
    """
    rows = technique.cached_removed_conditions
    if not rows:
        return None
    names = ", ".join(sorted({row.condition.name for row in rows}))
    return PayloadValuation(
        kind="dispel",
        label="dispel",
        value=0.0,
        provenance=ValuationProvenance.UNPRICED_DISPEL,
        detail=f"removes: {names}",
    )


def _capability_grant_valuations(technique: Technique) -> list[PayloadValuation]:
    """One INERT_PAYLOAD row per capability grant (#3279 Task 2) — explicitly zero.

    No technique/capability-grant cast seam exists anywhere in the codebase yet
    (see this app's CLAUDE.md, "Signature Motif Bonus" section's "Deferred" note,
    which documents the same gap for the sibling ``SignatureMotifBonusCapabilityGrant``
    payload) — valued 0 explicitly rather than silently dropped, so the report
    never implies a capability grant is combat-inert by omission.
    """
    return [
        PayloadValuation(
            kind="capability",
            label=grant.capability.name,
            value=0.0,
            provenance=ValuationProvenance.INERT_PAYLOAD,
            detail="no capability-grant cast seam exists (see src/world/magic/CLAUDE.md)",
        )
        for grant in technique.cached_capability_grants
    ]


def _all_payload_valuations(  # noqa: PLR0913 - cohesive per-technique valuation params
    technique: Technique,
    *,
    power: int,
    bands: list[_MatchupBand],
    context: EvalContext,
    reference: ReferenceFrame,
    multiplier_cache: dict[int, Decimal],
) -> list[PayloadValuation]:
    """Every payload valuation for *technique* at *power* (#3279 Task 2).

    Damage (Task 1) + applied-condition buffs/debuffs/control/mitigation +
    treatment heals + the one dispel row (if any) + one capability-grant row per
    grant (if any).
    """
    valuations = list(
        _damage_valuations(technique, power=power, bands=bands, multiplier_cache=multiplier_cache)
    )
    valuations.extend(
        _condition_application_valuations(
            technique,
            power=power,
            bands=bands,
            context=context,
            reference=reference,
            multiplier_cache=multiplier_cache,
        )
    )
    valuations.extend(_treatment_valuations(technique, bands=bands, reference=reference))
    dispel = _dispel_valuation(technique)
    if dispel is not None:
        valuations.append(dispel)
    valuations.extend(_capability_grant_valuations(technique))
    return valuations


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
    reference: ReferenceFrame,
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

    valuations = _all_payload_valuations(
        technique,
        power=baseline_power,
        bands=_bands,
        context=context,
        reference=reference,
        multiplier_cache=_multiplier_cache,
    )
    amplified_valuations = _all_payload_valuations(
        technique,
        power=amplified_power,
        bands=_bands,
        context=context,
        reference=reference,
        multiplier_cache=_multiplier_cache,
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


def evaluate_all_with_reference(
    context: EvalContext,
) -> tuple[list[TechniquePowerReport], ReferenceFrame]:
    """Evaluate every technique in the catalog, two-pass, exposing the reference (#3279).

    Pass 1 computes baseline attack DE for every technique carrying at least one
    damage-profile row; the median of those figures becomes the reference frame's
    ``outgoing_dpr``/``incoming_dpr`` (self-anchoring - derived from the game's own
    content, not an authored constant). Pass 2 evaluates every technique in the
    catalog against that reference. A run shares one matchup-band computation and
    one damage-multiplier cache across both passes and every technique.

    ``evaluate_all`` (below) is the pre-#3279-Task-3 signature every existing caller
    and test still uses; this wrapper is the one that also hands back the
    ``ReferenceFrame`` the two-pass bootstrap computed, for the Techniques tuning
    panel's "Reference DPR" line (`web.admin.tuning.technique_analytics`) - the only
    consumer of the reference frame outside this module.

    As of #3390, pass 1's bootstrap is extracted into
    ``de_valuation.compute_reference_frame`` (shared by the standalone condition and
    capability evaluators, so all three instruments anchor on the exact same median) -
    this function is now a thin wrapper: call that, then pass 2 as before.
    """
    reference = de_valuation.compute_reference_frame(context)

    multiplier_cache: dict[int, Decimal] = {}
    bands = _matchup_bands(context)
    all_techniques = Technique.objects.all().select_related("gift", "effect_type")
    reports = [
        evaluate_technique(
            technique, context, reference, _multiplier_cache=multiplier_cache, _bands=bands
        )
        for technique in all_techniques
    ]
    return reports, reference


def evaluate_all(context: EvalContext) -> list[TechniquePowerReport]:
    """Evaluate every technique in the catalog, two-pass (#3279).

    Thin wrapper over :func:`evaluate_all_with_reference` that drops the
    ``ReferenceFrame`` - kept as the stable pre-Task-3 signature for existing
    callers/tests that only want the reports.
    """
    reports, _reference = evaluate_all_with_reference(context)
    return reports
