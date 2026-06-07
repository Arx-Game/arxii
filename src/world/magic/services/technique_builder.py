"""Budget-based technique builder services (#537): config accessors,
pricing, authoring policies, and the build/author entry points."""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction

from world.magic.exceptions import TechniqueAuthoringNotPermitted, TechniqueBudgetExceeded
from world.magic.models import (
    Restriction,
    Technique,
    TechniqueAppliedCondition,
    TechniqueBudgetConfig,
    TechniqueCapabilityGrant,
    TechniqueDamageProfile,
    TechniqueTierBudget,
)
from world.magic.types.technique_builder import (
    TechniqueCostBreakdown,
    TechniqueCostLine,
    TechniqueDesignInput,
)

DEFAULT_TIER_POWER_BUDGET = {1: 20, 2: 40, 3: 60, 4: 80, 5: 100}
DEFAULT_TIER_REPRESENTATIVE_LEVEL = {1: 1, 2: 6, 3: 11, 4: 16, 5: 21}


def get_technique_budget_config() -> TechniqueBudgetConfig:
    """Get-or-create the budget config singleton (pk=1)."""
    with transaction.atomic():
        cfg, _ = TechniqueBudgetConfig.objects.get_or_create(pk=1)
        return cfg


def get_technique_tier_budget(tier: int) -> TechniqueTierBudget:
    """Get-or-create the per-tier budget row, seeding sane defaults."""
    with transaction.atomic():
        row, _ = TechniqueTierBudget.objects.get_or_create(
            tier=tier,
            defaults={
                "power_budget": DEFAULT_TIER_POWER_BUDGET.get(tier, 20 * tier),
                "representative_level": DEFAULT_TIER_REPRESENTATIVE_LEVEL.get(
                    tier, 1 + (tier - 1) * 5
                ),
                "label": f"Tier {tier}",
            },
        )
        return row


def create_technique(  # noqa: PLR0913
    *,
    creator,
    name,
    gift,
    style,
    effect_type,
    intensity,
    control,
    anima_cost,
    level,
    action_category,
    description,
    source_cantrip=None,
) -> Technique:
    """Low-level Technique row writer. Shared by cantrip finalization and
    build_technique. Does NOT create a CharacterTechnique."""
    return Technique.objects.create(
        name=name,
        gift=gift,
        style=style,
        effect_type=effect_type,
        intensity=intensity,
        control=control,
        anima_cost=anima_cost,
        level=level,
        action_category=action_category,
        description=description,
        source_cantrip=source_cantrip,
        creator=creator,
    )


def price_design(
    design: TechniqueDesignInput,
    *,
    config: TechniqueBudgetConfig,
    budget: int,
    restriction_bonus_total: int = 0,
    refunds_apply: bool = True,
) -> TechniqueCostBreakdown:
    """Pure pricing: itemize the design's power cost, subtract restriction
    refunds, and compare to the tier budget."""
    lines: list[TechniqueCostLine] = [
        TechniqueCostLine("intensity", "Intensity", design.intensity * config.intensity_unit_cost),
        TechniqueCostLine("control", "Control", design.control * config.control_unit_cost),
    ]
    for spec in design.capability_grants:
        value = int(spec.base_value + spec.intensity_multiplier * design.intensity)
        lines.append(
            TechniqueCostLine(
                "capability",
                "Capability grant",
                config.payload_base_cost + value * config.capability_value_unit_cost,
            )
        )
    for spec in design.damage_profiles:
        value = int(spec.base_damage + spec.damage_intensity_multiplier * design.intensity)
        lines.append(
            TechniqueCostLine(
                "damage",
                "Damage profile",
                config.payload_base_cost + value * config.damage_unit_cost,
            )
        )
    for spec in design.applied_conditions:
        dur = spec.base_duration_rounds or 0
        cost = (
            config.payload_base_cost
            + spec.base_severity * config.condition_severity_unit_cost
            + dur * config.condition_duration_unit_cost
        )
        lines.append(TechniqueCostLine("condition", "Applied condition", cost))

    gross = sum(line.power_cost for line in lines)
    refund = 0
    if refunds_apply:
        refund = int(Decimal(restriction_bonus_total) * config.restriction_refund_multiplier)
    total = max(0, gross - refund)
    return TechniqueCostBreakdown(
        tier=design.tier,
        budget=budget,
        lines=tuple(lines),
        gross_cost=gross,
        refund=refund,
        total_cost=total,
        within_budget=total <= budget,
    )


class AuthoringPolicy:
    """Base policy. Subclasses override the three knobs."""

    enforced: bool = True
    restriction_refunds_apply: bool = True

    def allowed_tiers(self, _character) -> set[int]:
        return {1, 2, 3, 4, 5}


class StaffPolicy(AuthoringPolicy):
    enforced = False  # budget is advisory


class PlayerPolicy(AuthoringPolicy):
    def allowed_tiers(self, _character) -> set[int]:
        # SEAM (#537): the research-unlock gate fills this. Permissive for now.
        # TODO(research-gate issue): restrict to tiers the character unlocked.
        return {1, 2, 3, 4, 5}


class GMPolicy(AuthoringPolicy):
    """Level-scaled GM policy. SEAM: calibration is staff-tunable/TODO —
    no grounded GM-level concept yet. Defaults to permissive enforced."""

    def allowed_tiers(self, _character) -> set[int]:
        # TODO(gm-calibration): scale by GM level once that concept exists.
        return {1, 2, 3, 4, 5}


def _restriction_bonus_total(design: TechniqueDesignInput) -> int:
    if not design.restriction_ids:
        return 0
    rows = Restriction.objects.filter(id__in=design.restriction_ids)
    return sum(r.power_bonus for r in rows)


def enforce_policy(
    design: TechniqueDesignInput,
    policy: AuthoringPolicy,
    character,
) -> TechniqueCostBreakdown:
    """Always prices and returns the breakdown; raises only when the policy
    is enforced and the design is over budget (or the tier is disallowed)."""
    if design.tier not in policy.allowed_tiers(character):
        raise TechniqueAuthoringNotPermitted
    budget = get_technique_tier_budget(design.tier).power_budget
    config = get_technique_budget_config()
    breakdown = price_design(
        design,
        config=config,
        budget=budget,
        restriction_bonus_total=_restriction_bonus_total(design),
        refunds_apply=policy.restriction_refunds_apply,
    )
    if policy.enforced and not breakdown.within_budget:
        raise TechniqueBudgetExceeded(breakdown)
    return breakdown


@transaction.atomic
def build_technique(design: TechniqueDesignInput, *, creator) -> Technique:
    """Unrestricted core: create the Technique + payload rows + restrictions.
    No pricing, no ceiling, no character binding. creator may be None (staff seed)."""
    from world.magic.models import EffectType, Gift, TechniqueStyle  # noqa: PLC0415

    tech = create_technique(
        creator=creator,
        name=design.name,
        gift=Gift.objects.get(pk=design.gift_id),
        style=TechniqueStyle.objects.get(pk=design.style_id),
        effect_type=EffectType.objects.get(pk=design.effect_type_id),
        intensity=design.intensity,
        control=design.control,
        anima_cost=design.anima_cost,
        level=design.level,
        action_category=design.action_category,
        description=design.description,
    )
    if design.restriction_ids:
        tech.restrictions.add(*Restriction.objects.filter(id__in=design.restriction_ids))
    for spec in design.capability_grants:
        TechniqueCapabilityGrant.objects.create(
            technique=tech,
            capability_id=spec.capability_id,
            base_value=spec.base_value,
            intensity_multiplier=spec.intensity_multiplier,
        )
    for spec in design.damage_profiles:
        TechniqueDamageProfile.objects.create(
            technique=tech,
            damage_type_id=spec.damage_type_id,
            base_damage=spec.base_damage,
            damage_intensity_multiplier=spec.damage_intensity_multiplier,
        )
    for spec in design.applied_conditions:
        TechniqueAppliedCondition.objects.create(
            technique=tech,
            condition_id=spec.condition_id,
            base_severity=spec.base_severity,
            base_duration_rounds=spec.base_duration_rounds,
        )
    return tech


@transaction.atomic
def author_technique(character, design: TechniqueDesignInput):
    """Player path: enforce PlayerPolicy, build, bind CharacterTechnique."""
    from world.magic.models import CharacterTechnique  # noqa: PLC0415

    breakdown = enforce_policy(design, PlayerPolicy(), character)
    tech = build_technique(design, creator=character)
    CharacterTechnique.objects.create(character=character, technique=tech)
    return tech, breakdown


@transaction.atomic
def author_staff_technique(design: TechniqueDesignInput, *, creator=None):
    """Staff path (base): StaffPolicy is advisory, build proceeds, no binding."""
    breakdown = enforce_policy(design, StaffPolicy(), creator)
    tech = build_technique(design, creator=creator)
    return tech, breakdown
