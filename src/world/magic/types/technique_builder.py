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
