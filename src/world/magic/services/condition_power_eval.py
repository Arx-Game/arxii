"""Standalone condition -> DE valuator (#3390).

Values a bare ``ConditionTemplate`` at a chosen severity/duration into DE (damage-
equivalent), independent of any technique that happens to apply it — today a
condition's DE figure only exists *entangled inside* whatever technique casts it (that
technique's own cast-SL distribution and duration). Reuses the exact shared formula core
``de_valuation.py`` extracted from ``technique_power_eval`` (never a second, drifting
implementation of the same math) — see that module's docstring. Drives the Game Tuning
"Conditions" panel's new DE column (``web.admin.tuning.condition_power_analytics``);
this module has no view/admin dependency of its own.

**Scope exclusions (Decision 6, issue #3390).** Two lanes the technique-level valuator
covers are NOT reachable standalone, and surface as a named ``UNPRICEABLE`` row rather
than a silent zero:

- The team-damage-percent lane needs a ``target_kind`` (ALLY vs ENEMY) to sign
  correctly, which only exists once a condition is wrapped in a technique's
  ``TechniqueAppliedCondition`` row — a bare ``ConditionTemplate`` has no such context.
- Stage-specific ``ConditionDamageOverTime`` rows are out of scope for parity with
  ``de_valuation.dot_per_round``'s own pre-existing condition-level-only scope
  (inherited unchanged from the technique valuator, documented there as a deliberate
  best-guess simplification).

Both are pre-existing gaps in the reused formula, not new scope this module adds.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import TYPE_CHECKING

from world.magic.services import capability_power_eval, de_valuation
from world.magic.types.condition_power import ConditionPowerReport
from world.magic.types.technique_power import (
    EvalContext,
    PayloadValuation,
    ReferenceFrame,
    ValuationProvenance,
)

if TYPE_CHECKING:
    from world.conditions.models import ConditionTemplate

#: Flags stamped on a ``ConditionPowerReport`` naming a Decision-6 scope exclusion.
TEAM_LANE_EXCLUDED_FLAG = "team_lane_excluded"
STAGE_DOT_EXCLUDED_FLAG = "stage_dot_excluded"


def _dot_row(
    template: ConditionTemplate, *, at_severity: int, duration_rounds: int
) -> PayloadValuation | None:
    """The DoT valuation row, if *template* carries condition-level DoT rows."""
    per_round = de_valuation.dot_per_round(template, severity=at_severity)
    if per_round is None:
        return None
    value = per_round * duration_rounds
    return PayloadValuation(
        kind="debuff",
        label=template.name,
        value=value,
        provenance=ValuationProvenance.FORMULA,
        detail=f"dot_per_round={per_round:.2f} x {duration_rounds} rounds",
    )


def _modifier_row(  # noqa: PLR0913 - cohesive per-row valuation params
    template: ConditionTemplate,
    *,
    at_severity: int,
    duration_rounds: int,
    context: EvalContext,
    multiplier_cache: dict[int, Decimal],
    bands: list[de_valuation.MatchupBand],
) -> PayloadValuation | None:
    """The generic check-modifier shift row, if *template* carries qualifying effects."""
    shift = de_valuation.modifier_effect_shift(template, severity=at_severity)
    if shift is None:
        return None

    shifted_roll_modifier = context.roll_modifier + round(shift)
    shifted_context = replace(context, roll_modifier=shifted_roll_modifier)
    shifted_bands = de_valuation.matchup_bands(shifted_context)
    base_de = de_valuation.reference_attack_de(
        bands, effective_power=context.level, multiplier_cache=multiplier_cache
    )
    shifted_de = de_valuation.reference_attack_de(
        shifted_bands, effective_power=context.level, multiplier_cache=multiplier_cache
    )
    delta = shifted_de - base_de
    value = delta * duration_rounds
    kind = "buff" if shift >= 0 else "debuff"
    return PayloadValuation(
        kind=kind,
        label=template.name,
        value=value,
        provenance=ValuationProvenance.ESTIMATE,
        detail=(f"shift={shift:.2f} -> DE delta {delta:.2f} x {duration_rounds} expected rounds"),
    )


def _mitigation_row(
    template: ConditionTemplate, *, duration_rounds: int, reference: ReferenceFrame
) -> PayloadValuation | None:
    """The mitigation-parse row, if *template*'s protective family parses."""
    result = de_valuation.mitigation_value(template, duration=duration_rounds, reference=reference)
    if result is None:
        return None
    value, detail = result
    return PayloadValuation(
        kind="mitigation",
        label=template.name,
        value=value,
        provenance=ValuationProvenance.PARSED,
        detail=detail,
    )


def _capability_effect_rows(
    template: ConditionTemplate,
    *,
    at_severity: int,
    context: EvalContext,
    reference: ReferenceFrame,
) -> list[PayloadValuation]:
    """One row per ``ConditionCapabilityEffect`` on *template* (#3390).

    magnitude = ``effect.value * (at_severity if effect.scales_with_severity else 1)``;
    priced by multiplying that magnitude against the effect's capability's own
    DE-per-point (``capability_power_eval.evaluate_capability``) — an ESTIMATE
    compounding two documented estimates, labeled as such in ``detail``.
    """
    from world.conditions.models import ConditionCapabilityEffect  # noqa: PLC0415

    effects = list(
        ConditionCapabilityEffect.objects.filter(condition=template).select_related("capability")
    )
    rows: list[PayloadValuation] = []
    for effect in effects:
        magnitude = effect.value * (at_severity if effect.scales_with_severity else 1)
        cap_report = capability_power_eval.evaluate_capability(
            effect.capability, context=context, reference=reference
        )
        value = magnitude * cap_report.total_de
        rows.append(
            PayloadValuation(
                kind="capability",
                label=f"{template.name} -> {effect.capability.name}",
                value=value,
                provenance=ValuationProvenance.ESTIMATE,
                detail=(
                    f"magnitude={magnitude:.2f} x capability DE/point "
                    f"{cap_report.total_de:.2f} (compounded estimate)"
                ),
            )
        )
    return rows


def evaluate_condition(
    template: ConditionTemplate,
    *,
    at_severity: int,
    duration_rounds: int,
    reference: ReferenceFrame,
    context: EvalContext | None = None,
    _multiplier_cache: dict[int, Decimal] | None = None,
    _bands: list[de_valuation.MatchupBand] | None = None,
) -> ConditionPowerReport:
    """Full DE report for one condition template at one severity/duration (#3390).

    ``context`` defaults to ``EvalContext()`` — its ``level``/``roll_modifier`` drive the
    synthetic reference-attack bands, same as the technique/capability evaluators'
    default matchup. ``_multiplier_cache``/``_bands`` let
    ``evaluate_all_conditions_with_reference`` share one damage-multiplier cache and one
    matchup-band computation across every condition in a run; a standalone caller
    computes its own (fresh per call) when omitted.

    Row order: DoT, generic check-modifier shift, mitigation parse, one row per
    ``ConditionCapabilityEffect``, then any Decision-6 scope-exclusion UNPRICEABLE gap
    rows, then a single UNPRICEABLE fallback row if NOTHING priced at all.
    """
    if context is None:
        context = EvalContext()
    if _multiplier_cache is None:
        _multiplier_cache = {}
    if _bands is None:
        _bands = de_valuation.matchup_bands(context)

    valuations: list[PayloadValuation] = []
    flags: list[str] = []

    dot_row = _dot_row(template, at_severity=at_severity, duration_rounds=duration_rounds)
    if dot_row is not None:
        valuations.append(dot_row)

    modifier_row = _modifier_row(
        template,
        at_severity=at_severity,
        duration_rounds=duration_rounds,
        context=context,
        multiplier_cache=_multiplier_cache,
        bands=_bands,
    )
    if modifier_row is not None:
        valuations.append(modifier_row)

    mitigation_row = _mitigation_row(template, duration_rounds=duration_rounds, reference=reference)
    if mitigation_row is not None:
        valuations.append(mitigation_row)

    valuations.extend(
        _capability_effect_rows(
            template, at_severity=at_severity, context=context, reference=reference
        )
    )

    if de_valuation.is_team_lane_condition(template):
        flags.append(TEAM_LANE_EXCLUDED_FLAG)
        valuations.append(
            PayloadValuation(
                kind="debuff",
                label=template.name,
                value=0.0,
                provenance=ValuationProvenance.UNPRICEABLE,
                detail=(
                    "team-damage-percent lane needs a technique-wrapper target_kind; "
                    "not priceable standalone"
                ),
            )
        )
    if de_valuation.has_stage_scoped_dot(template):
        flags.append(STAGE_DOT_EXCLUDED_FLAG)
        valuations.append(
            PayloadValuation(
                kind="debuff",
                label=template.name,
                value=0.0,
                provenance=ValuationProvenance.UNPRICEABLE,
                detail="stage-scoped DoT rows are out of scope for standalone condition valuation",
            )
        )

    if not valuations:
        valuations.append(
            PayloadValuation(
                kind="unpriceable",
                label=template.name,
                value=0.0,
                provenance=ValuationProvenance.UNPRICEABLE,
                detail="unrecognized payload shape",
            )
        )

    total_de = sum(v.value for v in valuations)
    return ConditionPowerReport(
        template_id=template.pk,
        name=template.name,
        at_severity=at_severity,
        duration_rounds=duration_rounds,
        total_de=total_de,
        valuations=tuple(valuations),
        flags=tuple(flags),
    )


def evaluate_all_conditions_with_reference(
    context: EvalContext, *, at_severity: int, duration_rounds: int
) -> tuple[list[ConditionPowerReport], ReferenceFrame]:
    """Evaluate every ``ConditionTemplate`` against one shared reference (#3390).

    Mirrors ``technique_power_eval.evaluate_all_with_reference``'s two-pass sharing:
    ``de_valuation.compute_reference_frame`` anchors on the SAME median-attack reference
    every other instrument uses (Decision 2), then one shared matchup-band computation
    and damage-multiplier cache prices every condition template in the catalog.
    """
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415

    reference = de_valuation.compute_reference_frame(context)

    multiplier_cache: dict[int, Decimal] = {}
    bands = de_valuation.matchup_bands(context)

    templates = ConditionTemplate.objects.all()
    reports = [
        evaluate_condition(
            template,
            at_severity=at_severity,
            duration_rounds=duration_rounds,
            reference=reference,
            context=context,
            _multiplier_cache=multiplier_cache,
            _bands=bands,
        )
        for template in templates
    ]
    return reports, reference
