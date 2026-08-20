"""Technique combat-power evaluator types (#3279).

Shared shapes for ``world.magic.services.technique_power_eval`` — the panel-driving
evaluator that prices every authored technique's combat payloads into DE (damage
equivalent per cast in a reference matchup) and compares its baseline power to a
"fully matched anchor" (a caster with an engaged covenant role/specialty at the
panel's thread level). See ``docs/plans/3279-technique-power-eval-plan.md`` for the
full currency spec.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ValuationProvenance(str, Enum):
    """How confident a ``PayloadValuation``'s ``value`` figure is (#3279).

    FORMULA
        Derived directly from an authored formula (a damage budget, a priced
        percent severity) with no approximation.
    PARSED
        Derived by walking authored structure (a mitigation flow step's
        MODIFY_PAYLOAD factor) rather than reading one formula field.
    ESTIMATE
        A deliberate approximation where no exact formula exists (hard
        control's expected-duration x reference incoming DPR).
    UNPRICED_DISPEL
        A ``TechniqueRemovedCondition`` payload — not priced in v1; listed
        value is always 0.
    UNPRICEABLE
        The payload's mechanism could not be classified at all — an
        authoring-gap bucket row, value 0.
    INERT_PAYLOAD
        A capability grant with no cast seam yet — valued 0 explicitly, not
        silently dropped.
    """

    FORMULA = "FORMULA"
    PARSED = "PARSED"
    ESTIMATE = "ESTIMATE"
    UNPRICED_DISPEL = "UNPRICED_DISPEL"
    UNPRICEABLE = "UNPRICEABLE"
    INERT_PAYLOAD = "INERT_PAYLOAD"


@dataclass(frozen=True, slots=True)
class EvalContext:
    """Panel knobs driving one technique-power evaluation run (#3279).

    ``roller_points``/``target_difficulty``/``roll_modifier`` mirror the
    checks-analytics tuning panel's own matchup knobs
    (``web.admin.tuning.checks_analytics.compute_matchup``). ``level`` and
    ``thread_level`` drive the role-band comparison: baseline power is the
    technique's own intensity; amplified power adds the blend + specialty
    pure-helper contributions at ``thread_level`` for a "fully matched
    anchor" caster.
    """

    level: int = 10
    thread_level: int = 3
    roller_points: int = 25
    target_difficulty: int = 25
    roll_modifier: int = 0


@dataclass(frozen=True, slots=True)
class ReferenceFrame:
    """Self-anchoring reference DPR for one evaluation run (#3279).

    Built by ``evaluate_all``'s pass 1: both DPR figures default to the
    median baseline attack DE across every technique carrying damage-profile
    rows, so the reference is derived from the game's own authored content
    rather than a hand-picked constant. ``source_label`` documents where the
    number came from for the panel drill-down (e.g. "median-attack estimate",
    or "no attack techniques" when pass 1 found nothing to median).
    """

    outgoing_dpr: float
    incoming_dpr: float
    source_label: str


@dataclass(frozen=True, slots=True)
class PayloadValuation:
    """One priced payload line inside a technique's combat-power report (#3279)."""

    #: "damage" / "buff" / "debuff" / "control" / "mitigation" / "heal" /
    #: "dispel" / "capability".
    kind: str
    label: str
    value: float
    provenance: ValuationProvenance
    #: Human-readable arithmetic, e.g. "E[budget x mult] over SL bands = 14.2".
    detail: str


@dataclass(frozen=True, slots=True)
class TechniquePowerReport:
    """Full combat-power report for one technique at one evaluation context (#3279)."""

    technique_id: int
    name: str
    gift_name: str
    level: int
    tier: int
    category: str
    baseline_power: int
    amplified_power: int
    baseline_de: float
    amplified_de: float
    #: Priced payload lines for the BASELINE context (power=baseline_power).
    valuations: tuple[PayloadValuation, ...]
    effective_anima: int
    de_per_anima: float
    #: e.g. "weapon_scaled", "windup:2", "passive", "no_result_charts".
    flags: tuple[str, ...]
