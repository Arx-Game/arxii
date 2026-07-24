"""Frozen value types for the technique builder (#537)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CapabilityGrantSpec:
    capability_id: int
    base_value: int = 0
    intensity_multiplier: float = 0.0


@dataclass(frozen=True)
class DamageProfileSpec:
    damage_type_id: int | None
    base_damage: int = 0
    damage_intensity_multiplier: float = 0.0


@dataclass(frozen=True)
class AppliedConditionSpec:
    condition_id: int
    base_severity: int = 1
    base_duration_rounds: int | None = None


@dataclass(frozen=True)
class RemovedConditionSpec:
    """A dispel/cleanse payload row for technique authoring (#1585).

    Diverges from ``AppliedConditionSpec`` by carrying ``target_kind`` and
    ``minimum_success_level`` as authored fields. The apply path hardcodes these
    (ENEMY / 1 via model defaults) and does not expose them to authors, but a
    dispel technique must support SELF (cleanse) and ALLY (ally-debuff-strip)
    targeting, so removal authors them explicitly. The inert severity/duration
    knobs are not present (removal neither applies severity nor duration).
    """

    condition_id: int
    target_kind: str = "enemy"
    minimum_success_level: int = 1
    remove_all_stacks: bool = True


@dataclass(frozen=True)
class TreatmentSpec:
    """A treatment payload row for technique authoring (#2668).

    Points at a TreatmentTemplate; the technique-cast path calls perform_treatment
    with the caster as helper. target_kind defaults to ALLY (healing is
    ally-directed); minimum_success_level defaults to 1.
    """

    treatment_template_id: int
    target_kind: str = "ally"
    minimum_success_level: int = 1


@dataclass(frozen=True)
class TechniqueDesignInput:
    name: str
    description: str
    gift_id: int
    style_id: int
    effect_type_id: int
    action_category: str
    tier: int
    intensity: int
    control: int
    anima_cost: int
    level: int
    restriction_ids: tuple[int, ...] = ()
    capability_grants: tuple[CapabilityGrantSpec, ...] = ()
    damage_profiles: tuple[DamageProfileSpec, ...] = ()
    applied_conditions: tuple[AppliedConditionSpec, ...] = ()
    removed_conditions: tuple[RemovedConditionSpec, ...] = ()
    treatments: tuple[TreatmentSpec, ...] = ()
    consequence_pool_id: int | None = None


@dataclass(frozen=True)
class TechniqueCostLine:
    dimension: str
    label: str
    power_cost: int


@dataclass(frozen=True)
class TechniqueCostBreakdown:
    tier: int
    budget: int
    lines: tuple[TechniqueCostLine, ...] = field(default_factory=tuple)
    gross_cost: int = 0
    refund: int = 0
    total_cost: int = 0
    within_budget: bool = True
