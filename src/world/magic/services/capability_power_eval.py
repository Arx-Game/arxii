"""Capability -> DE valuator (#3390).

Prices what one point of a ``CapabilityType`` mechanically buys, on the same DE
(damage-equivalent) currency ``technique_power_eval`` and ``condition_power_eval`` use —
see ``world.magic.services.de_valuation``'s module docstring for the shared-currency
rationale. Drives the Game Tuning "Capabilities" panel
(``web.admin.tuning.capability_power_analytics``); this module has no view/admin
dependency of its own.

**Pricing model (Decision 3, issue #3390).** Post-#2704/#2708, a capability's mechanical
value flows into checks entirely through authored ``CheckTypeCapabilityModifier`` rows —
each row's ``weight`` is the exact pre-truncation marginal rate (the derivative of
``weight * (value - baseline)`` w.r.t. ``value`` is ``weight``). This evaluator treats that
weight directly as a synthetic ``roll_modifier`` shift and measures its DE impact via the
same synthetic-reference-attack machinery (``de_valuation.reference_attack_de``) the
technique/condition generic-modifier valuators use. This is a documented ESTIMATE-
provenance linear approximation, not the full truncated/largest-remainder allocation
(``world.checks.services._capability_point_allocation``) — that allocation needs a real
``CharacterSheet``'s simultaneous capability set, which doesn't exist for "one abstract
point of capability X" (see the issue's Decision 3 for the full reasoning).

**No authored bridge = 0 DE, not a crash (Decision 5).** A capability with zero authored
``CheckTypeCapabilityModifier`` rows prices at exactly 0.0 with an ``"no_authored_bridge"``
flag — correct behavior today (no production seeder authors these rows yet), not a gap.

**Guardian-reaction leg needs no bespoke code (Decision 4).** Guardian reactions resolve
through ordinary ``CheckType``s (Reflexes, Melee Defense) via ``compute_check_rating`` —
this evaluator already iterates every authored ``CheckTypeCapabilityModifier`` row across
every ``CheckType``, so a guardian-reaction bridge row prices itself automatically the
moment staff author one; no separate "guardian" code path exists or is needed.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import TYPE_CHECKING

from world.magic.services import de_valuation
from world.magic.types.capability_power import CapabilityPowerReport
from world.magic.types.technique_power import (
    EvalContext,
    PayloadValuation,
    ReferenceFrame,
    ValuationProvenance,
)

if TYPE_CHECKING:
    from world.conditions.models import CapabilityType

#: Flag stamped on a ``CapabilityPowerReport`` for a capability with zero authored
#: ``CheckTypeCapabilityModifier`` rows (Decision 5) — 0 DE WITH this flag is correct
#: behavior, distinguishing "genuinely worth nothing today" from "nobody's wired it in."
NO_AUTHORED_BRIDGE_FLAG = "no_authored_bridge"


def evaluate_capability(
    capability: CapabilityType,
    *,
    context: EvalContext,
    reference: ReferenceFrame,
    _multiplier_cache: dict[int, Decimal] | None = None,
    _bands: list[de_valuation.MatchupBand] | None = None,
) -> CapabilityPowerReport:
    """Full DE report for one capability at one evaluation context (#3390).

    Prices every authored ``CheckTypeCapabilityModifier`` row for *capability* as a
    marginal ``roll_modifier`` shift (Decision 3) measured against the synthetic
    reference attack. ``_multiplier_cache``/``_bands`` let
    ``evaluate_all_capabilities_with_reference`` share one damage-multiplier cache and
    one matchup-band computation across every capability in a run; a standalone caller
    computes its own (fresh per call) when omitted.
    """
    from world.checks.models import CheckTypeCapabilityModifier  # noqa: PLC0415

    if _multiplier_cache is None:
        _multiplier_cache = {}
    if _bands is None:
        _bands = de_valuation.matchup_bands(context)

    rows = list(
        CheckTypeCapabilityModifier.objects.filter(capability=capability).select_related(
            "check_type"
        )
    )
    if not rows:
        return CapabilityPowerReport(
            capability_id=capability.pk,
            name=capability.name,
            total_de=0.0,
            valuations=(
                PayloadValuation(
                    kind="check_bridge",
                    label="no check bridge",
                    value=0.0,
                    provenance=ValuationProvenance.UNPRICEABLE,
                    detail=(
                        "no authored CheckTypeCapabilityModifier rows for this "
                        f"capability (reference: {reference.source_label})"
                    ),
                ),
            ),
            flags=(NO_AUTHORED_BRIDGE_FLAG,),
        )

    base_de = de_valuation.reference_attack_de(
        _bands, effective_power=context.level, multiplier_cache=_multiplier_cache
    )

    valuations: list[PayloadValuation] = []
    for row in rows:
        raw_shift = float(row.weight)
        shifted_roll_modifier = context.roll_modifier + round(raw_shift)
        shifted_context = replace(context, roll_modifier=shifted_roll_modifier)
        shifted_bands = de_valuation.matchup_bands(shifted_context)
        shifted_de = de_valuation.reference_attack_de(
            shifted_bands, effective_power=context.level, multiplier_cache=_multiplier_cache
        )
        delta = shifted_de - base_de
        valuations.append(
            PayloadValuation(
                kind="check_bridge",
                label=row.check_type.name,
                value=delta,
                provenance=ValuationProvenance.ESTIMATE,
                detail=(
                    f"weight={raw_shift:.2f} -> roll_modifier shift {round(raw_shift)} -> "
                    f"DE delta {delta:.2f} (reference: {reference.source_label})"
                ),
            )
        )

    total_de = sum(v.value for v in valuations)
    return CapabilityPowerReport(
        capability_id=capability.pk,
        name=capability.name,
        total_de=total_de,
        valuations=tuple(valuations),
        flags=(),
    )


def evaluate_all_capabilities_with_reference(
    context: EvalContext,
) -> tuple[list[CapabilityPowerReport], ReferenceFrame]:
    """Evaluate every ``CapabilityType`` in the catalog against one shared reference (#3390).

    Mirrors ``technique_power_eval.evaluate_all_with_reference``'s two-pass sharing:
    ``de_valuation.compute_reference_frame`` anchors on the SAME median-attack reference
    every other instrument uses (Decision 2), then one shared matchup-band computation
    and damage-multiplier cache prices every capability in the catalog.
    """
    from world.conditions.models import CapabilityType  # noqa: PLC0415

    reference = de_valuation.compute_reference_frame(context)

    multiplier_cache: dict[int, Decimal] = {}
    bands = de_valuation.matchup_bands(context)

    capabilities = CapabilityType.objects.all()
    reports = [
        evaluate_capability(
            capability,
            context=context,
            reference=reference,
            _multiplier_cache=multiplier_cache,
            _bands=bands,
        )
        for capability in capabilities
    ]
    return reports, reference
