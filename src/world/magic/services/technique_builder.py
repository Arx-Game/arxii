"""Budget-based technique builder services (#537): config accessors,
pricing, authoring policies, and the build/author entry points."""

from __future__ import annotations

from decimal import Decimal
import logging

from django.db import transaction

from world.magic.exceptions import (
    DuplicateTechniqueName,
    GiftNotOwned,
    TechniqueAuthoringNotPermitted,
    TechniqueBudgetExceeded,
    UnknownGift,
)
from world.magic.models import (
    Restriction,
    Technique,
    TechniqueAppliedCondition,
    TechniqueBudgetConfig,
    TechniqueCapabilityGrant,
    TechniqueDamageProfile,
    TechniqueRemovedCondition,
    TechniqueTierBudget,
    TechniqueTreatment,
)
from world.magic.types.technique_builder import (
    TechniqueCostBreakdown,
    TechniqueCostLine,
    TechniqueDesignInput,
)

logger = logging.getLogger(__name__)

DEFAULT_TIER_POWER_BUDGET = {1: 20, 2: 40, 3: 60, 4: 80, 5: 100}
DEFAULT_TIER_REPRESENTATIVE_LEVEL = {1: 1, 2: 6, 3: 11, 4: 16, 5: 21}


def get_technique_budget_config() -> TechniqueBudgetConfig:
    """Get-or-create the budget config singleton (pk=1)."""
    with transaction.atomic():
        cfg = TechniqueBudgetConfig.objects.cached_singleton()
    if cfg is None:
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


def get_technique_cast_catalog():
    """Curated catalog: children of the base 'Magic: Technique Cast' ConsequencePool."""
    from actions.models import ConsequencePool  # noqa: PLC0415
    from world.magic.seeds_cast import get_standalone_cast_pool  # noqa: PLC0415

    return ConsequencePool.objects.filter(parent=get_standalone_cast_pool()).order_by("name")


def get_combat_offense_catalog():
    """Curated catalog: children of the base 'Combat: Melee Offense' ConsequencePool (#1995)."""
    from actions.models import ConsequencePool  # noqa: PLC0415
    from world.combat.seeds_offense import get_melee_offense_pool  # noqa: PLC0415

    return ConsequencePool.objects.filter(parent=get_melee_offense_pool()).order_by("name")


def _resolve_catalog_template(consequence_pool_id: int, catalog):
    """Validate ``consequence_pool_id`` is a member of ``catalog``, then resolve the
    matching ActionTemplate. Raises InvalidConsequencePoolChoice for a non-member id
    (including a valid-but-unrelated or wrong-category ConsequencePool)."""
    from actions.models import ActionTemplate  # noqa: PLC0415
    from world.magic.exceptions import InvalidConsequencePoolChoice  # noqa: PLC0415

    if not catalog.filter(pk=consequence_pool_id).exists():
        raise InvalidConsequencePoolChoice
    matches = list(
        ActionTemplate.objects.filter(consequence_pool_id=consequence_pool_id).order_by("pk")[:2]
    )
    if len(matches) > 1:
        logger.warning(
            "Multiple ActionTemplate rows point at ConsequencePool %s; using the oldest "
            "(pk=%s). This is a data-integrity issue — a catalog ConsequencePool should "
            "have exactly one matching ActionTemplate.",
            consequence_pool_id,
            matches[0].pk,
        )
    return matches[0]


def resolve_cast_action_template(
    consequence_pool_id: int | None, *, action_category: str | None = None
):
    """Resolve the ActionTemplate a technique's action_template should point at.

    None (no flavor chosen) resolves to the shared base template — today's
    unchanged default for non-physical categories. A PHYSICAL technique with
    no chosen pool resolves to the combat 'Melee Attack' ActionTemplate (#1706)
    so physical attacks roll a combat check (strength + Melee Combat) instead
    of the magic fallback.

    A chosen consequence_pool_id validates against the catalog matching the
    technique's action_category (#1995): PHYSICAL validates against the combat
    'Combat: Melee Offense' catalog (``get_combat_offense_catalog``); every other
    category validates against the magic 'Magic: Technique Cast' catalog
    (``get_technique_cast_catalog``). Raises InvalidConsequencePoolChoice for a
    pool id that isn't a member of the relevant catalog — including a
    valid-but-wrong-category catalog pool (e.g. a magic flavor chosen for a
    PHYSICAL technique) or an unrelated ConsequencePool.
    """
    from actions.constants import ActionCategory  # noqa: PLC0415
    from world.magic.seeds_cast import get_standalone_cast_template  # noqa: PLC0415

    is_physical = action_category == ActionCategory.PHYSICAL

    if consequence_pool_id is None:
        if is_physical:
            from world.combat.factories import wire_melee_attack_action_template  # noqa: PLC0415

            return wire_melee_attack_action_template()
        return get_standalone_cast_template()

    if is_physical:
        return _resolve_catalog_template(consequence_pool_id, get_combat_offense_catalog())
    return _resolve_catalog_template(consequence_pool_id, get_technique_cast_catalog())


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
    action_template=None,
) -> Technique:
    """Low-level Technique row writer. Shared by build_technique and the CG
    starter-gift catalog seed. Does NOT create a CharacterTechnique.

    Defaults action_template to the shared 'Technique Cast' template so every
    technique is castable standalone; pass an explicit template to override.

    Raises:
        DuplicateTechniqueName: if a Technique already exists for this (gift, name) —
            pre-checked ahead of the INSERT so a name collision fails clean instead of
            an unhandled IntegrityError against the ``unique_technique_name_per_gift``
            DB constraint (#2486).
    """
    if action_template is None:
        from world.magic.seeds_cast import get_standalone_cast_template  # noqa: PLC0415

        action_template = get_standalone_cast_template()
    with transaction.atomic():
        if Technique.objects.filter(gift=gift, name=name).exists():
            raise DuplicateTechniqueName
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
            creator=creator,
            action_template=action_template,
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
    lines.extend(
        TechniqueCostLine(
            "condition",
            "Removed condition (dispel)",
            config.payload_base_cost,
        )
        for _spec in design.removed_conditions
    )
    lines.extend(
        TechniqueCostLine(
            "condition",
            "Treatment (bounded mend)",
            config.payload_base_cost,
        )
        for _spec in design.treatments
    )

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
        action_template=resolve_cast_action_template(
            design.consequence_pool_id, action_category=design.action_category
        ),
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
    for spec in design.removed_conditions:
        # Removal rows carry no severity/duration/stack — leave the inherited
        # defaults (enforced by TechniqueRemovedCondition.clean()). Only the
        # authorable removal fields are set (#1585).
        TechniqueRemovedCondition.objects.create(
            technique=tech,
            condition_id=spec.condition_id,
            target_kind=spec.target_kind,
            minimum_success_level=spec.minimum_success_level,
            remove_all_stacks=spec.remove_all_stacks,
        )
    for spec in design.treatments:
        from world.conditions.models import TreatmentTemplate  # noqa: PLC0415

        TechniqueTreatment.objects.create(
            technique=tech,
            treatment_template=TreatmentTemplate.objects.get(pk=spec.treatment_template_id),
            target_kind=spec.target_kind,
            minimum_success_level=spec.minimum_success_level,
        )
    return tech


def validate_design_for_character(
    design: TechniqueDesignInput,
    policy: AuthoringPolicy,
    character,
) -> None:
    """Enforce the player design gate: gift existence + ownership for PlayerPolicy.

    No-op for StaffPolicy (any gift is allowed, staff bypass ownership check).

    This is the single shared gate used by both the telnet command and the web
    serializer, so both paths enforce the same rules.

    Raises:
        UnknownGift: if the gift id does not resolve to a known Gift.
        GiftNotOwned: if the player does not own the resolved gift.
    """
    if not isinstance(policy, PlayerPolicy):
        return
    from world.magic.models import CharacterGift, Gift  # noqa: PLC0415

    if not Gift.objects.filter(pk=design.gift_id).exists():
        raise UnknownGift
    if (
        character is None
        or not CharacterGift.objects.filter(character=character, gift_id=design.gift_id).exists()
    ):
        raise GiftNotOwned


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
