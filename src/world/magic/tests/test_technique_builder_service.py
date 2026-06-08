from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.exceptions import TechniqueBudgetExceeded
from world.magic.factories import (
    CharacterGiftFactory,
    EffectTypeFactory,
    GiftFactory,
    RestrictionFactory,
    TechniqueStyleFactory,
)
from world.magic.models import (
    CharacterTechnique,
    Technique,
    TechniqueBudgetConfig,
    TechniqueTierBudget,
)
from world.magic.services.technique_builder import (
    PlayerPolicy,
    StaffPolicy,
    author_staff_technique,
    author_technique,
    build_technique,
    create_technique,
    enforce_policy,
    get_technique_budget_config,
    get_technique_tier_budget,
    price_design,
)
from world.magic.types.technique_builder import (
    AppliedConditionSpec,
    CapabilityGrantSpec,
    DamageProfileSpec,
    TechniqueDesignInput,
)


def _design(**over):
    base = {
        "name": "X",
        "description": "",
        "gift_id": 1,
        "style_id": 1,
        "effect_type_id": 1,
        "action_category": "physical",
        "tier": 1,
        "intensity": 3,
        "control": 2,
        "anima_cost": 2,
        "level": 1,
    }
    base.update(over)
    return TechniqueDesignInput(**base)


class ConfigAccessorTests(TestCase):
    def test_config_lazy_created(self):
        assert TechniqueBudgetConfig.objects.count() == 0
        cfg = get_technique_budget_config()
        assert cfg.pk == 1
        assert TechniqueBudgetConfig.objects.count() == 1

    def test_tier_budget_lazy_defaults(self):
        row = get_technique_tier_budget(3)
        assert row.tier == 3
        assert row.power_budget == 60
        assert row.representative_level == 11
        assert TechniqueTierBudget.objects.get(tier=3).pk == row.pk


class CreateTechniqueHelperTests(TestCase):
    def test_create_technique_minimal(self):
        sheet = CharacterSheetFactory()
        gift = GiftFactory(creator=sheet)
        tech = create_technique(
            creator=sheet,
            name="Spark",
            gift=gift,
            style=TechniqueStyleFactory(),
            effect_type=EffectTypeFactory(),
            intensity=3,
            control=2,
            anima_cost=2,
            level=1,
            action_category="physical",
            description="",
        )
        assert isinstance(tech, Technique)
        assert tech.creator_id == sheet.pk
        # helper does NOT bind a CharacterTechnique
        assert not CharacterTechnique.objects.filter(technique=tech).exists()


class PriceDesignTests(TestCase):
    def test_core_stats_priced(self):
        cfg = get_technique_budget_config()
        bd = price_design(_design(), config=cfg, budget=20)
        # intensity 3*1 + control 2*1 = 5
        assert bd.gross_cost == 5
        assert bd.total_cost == 5
        assert bd.within_budget is True

    def test_damage_payload_and_over_budget(self):
        cfg = get_technique_budget_config()
        d = _design(
            intensity=10,
            control=10,
            damage_profiles=(DamageProfileSpec(damage_type_id=None, base_damage=5),),
        )
        bd = price_design(d, config=cfg, budget=20)
        # 10 + 10 + (payload_base 2 + damage 5*1) = 27
        assert bd.gross_cost == 27
        assert bd.within_budget is False


class PolicyTests(TestCase):
    def test_staff_advisory_never_raises_but_returns_breakdown(self):
        sheet = CharacterSheetFactory()
        d = _design(intensity=100, control=100, tier=1)
        bd = enforce_policy(d, StaffPolicy(), sheet)
        assert bd.within_budget is False  # reported
        # no raise

    def test_player_enforced_raises_over_budget(self):
        sheet = CharacterSheetFactory()
        d = _design(intensity=100, control=100, tier=1)
        with self.assertRaises(TechniqueBudgetExceeded):
            enforce_policy(d, PlayerPolicy(), sheet)


class BuildTechniqueTests(TestCase):
    def test_build_unbound_with_payloads(self):
        sheet = CharacterSheetFactory()
        gift = GiftFactory(creator=sheet)
        d = _design(
            gift_id=gift.id,
            style_id=TechniqueStyleFactory().id,
            effect_type_id=EffectTypeFactory().id,
            tier=1,
            level=1,
        )
        tech = build_technique(d, creator=None)
        assert tech.creator_id is None
        assert tech.level == 1
        assert not CharacterTechnique.objects.filter(technique=tech).exists()


class WrapperTests(TestCase):
    def test_player_within_budget_binds_character(self):
        sheet = CharacterSheetFactory()
        gift = GiftFactory(creator=sheet)
        CharacterGiftFactory(character=sheet, gift=gift)
        d = _design(
            gift_id=gift.id,
            style_id=TechniqueStyleFactory().id,
            effect_type_id=EffectTypeFactory().id,
            intensity=3,
            control=2,
        )
        tech, bd = author_technique(sheet, d)
        assert bd.within_budget is True
        assert CharacterTechnique.objects.filter(character=sheet, technique=tech).exists()

    def test_player_over_budget_no_partial_rows(self):
        sheet = CharacterSheetFactory()
        gift = GiftFactory(creator=sheet)
        d = _design(
            gift_id=gift.id,
            style_id=TechniqueStyleFactory().id,
            effect_type_id=EffectTypeFactory().id,
            intensity=100,
            control=100,
        )
        before = Technique.objects.count()
        with self.assertRaises(TechniqueBudgetExceeded):
            author_technique(sheet, d)
        assert Technique.objects.count() == before  # atomic rollback

    def test_staff_over_budget_succeeds_unbound(self):
        sheet = CharacterSheetFactory()
        gift = GiftFactory(creator=sheet)
        d = _design(
            gift_id=gift.id,
            style_id=TechniqueStyleFactory().id,
            effect_type_id=EffectTypeFactory().id,
            intensity=100,
            control=100,
        )
        tech, bd = author_staff_technique(d)
        assert bd.within_budget is False
        assert tech.creator_id is None


# =============================================================================
# §9 pricing tests: tier-bump, restriction refund, capability/condition lines
# =============================================================================


class TierBudgetEnforcementTests(TestCase):
    """§9 tier-bump: verify over-budget at tier N but within budget at tier N+1."""

    def test_over_budget_at_tier1_within_budget_at_tier2(self):
        """Tier 1 default budget is 20. Tier 2 budget is 40.
        intensity=15, control=15 → gross_cost=30: over T1, within T2.
        """
        cfg = get_technique_budget_config()

        tier1 = get_technique_tier_budget(1)
        tier2 = get_technique_tier_budget(2)
        # Tier 1 budget is 20 by default; tier 2 is 40.
        assert tier1.power_budget == 20
        assert tier2.power_budget == 40

        d_t1 = _design(intensity=15, control=15, tier=1, level=tier1.representative_level)
        bd_t1 = price_design(d_t1, config=cfg, budget=tier1.power_budget)
        assert bd_t1.within_budget is False  # 15+15=30 > 20

        d_t2 = _design(intensity=15, control=15, tier=2, level=tier2.representative_level)
        bd_t2 = price_design(d_t2, config=cfg, budget=tier2.power_budget)
        assert bd_t2.within_budget is True  # 30 <= 40

    def test_enforce_policy_raises_at_tier1_passes_at_tier2(self):
        """enforce_policy with PlayerPolicy raises at tier 1, succeeds at tier 2."""
        sheet = CharacterSheetFactory()
        tier1 = get_technique_tier_budget(1)
        tier2 = get_technique_tier_budget(2)
        d_t1 = _design(intensity=15, control=15, tier=1, level=tier1.representative_level)
        with self.assertRaises(TechniqueBudgetExceeded):
            enforce_policy(d_t1, PlayerPolicy(), sheet)

        d_t2 = _design(intensity=15, control=15, tier=2, level=tier2.representative_level)
        bd = enforce_policy(d_t2, PlayerPolicy(), sheet)
        assert bd.within_budget is True


class RestrictionRefundTests(TestCase):
    """§9 restriction refund: a design that fails without Restriction passes with one."""

    def test_refund_raises_effective_budget(self):
        """intensity=18, control=2 → gross_cost=20 at tier 1 (budget=20): exactly on limit.
        Add a Restriction with power_bonus=10 and restriction_refund_multiplier=1.0
        → refund=10 → total=10, clearly within budget.

        Without restriction: total=20 == 20, within_budget True (edge). So bump intensity
        to 19 to ensure without-restriction is False.
        """
        cfg = get_technique_budget_config()
        cfg.restriction_refund_multiplier = 1  # 100% refund
        # intensity=19, control=2 → gross=21, budget=20: over without refund
        d_no_restriction = _design(intensity=19, control=2)
        bd_no = price_design(d_no_restriction, config=cfg, budget=20)
        assert bd_no.within_budget is False  # 21 > 20

        restriction = RestrictionFactory(power_bonus=10)
        d_with_restriction = _design(
            intensity=19,
            control=2,
            restriction_ids=(restriction.id,),
        )
        bd_yes = price_design(
            d_with_restriction,
            config=cfg,
            budget=20,
            restriction_bonus_total=restriction.power_bonus,
            refunds_apply=True,
        )
        # gross=21, refund=10 → total=11, within 20
        assert bd_yes.within_budget is True
        assert bd_yes.refund == 10


class CapabilityConditionPricingLineTests(TestCase):
    """§9 capability + condition pricing: verify each contributes expected cost line."""

    def test_capability_grant_line_cost(self):
        """A capability grant spec contributes payload_base_cost + value*capability_value_unit_cost.

        Default config: payload_base_cost=2, capability_value_unit_cost=1.
        Spec: base_value=3, intensity_multiplier=0.0, design.intensity=5.
        effective_value = int(3 + 0.0*5) = 3.
        line_cost = 2 + 3*1 = 5.
        """
        cfg = get_technique_budget_config()
        # Use an arbitrary capability_id — price_design reads spec values only, not the DB row.
        cap_spec = CapabilityGrantSpec(capability_id=9999, base_value=3, intensity_multiplier=0.0)
        d = _design(intensity=5, control=0, capability_grants=(cap_spec,))
        bd = price_design(d, config=cfg, budget=200)

        cap_lines = [line for line in bd.lines if line.dimension == "capability"]
        assert len(cap_lines) == 1, f"Expected 1 capability line, got {cap_lines}"
        expected_cost = cfg.payload_base_cost + 3 * cfg.capability_value_unit_cost
        assert cap_lines[0].power_cost == expected_cost

    def test_applied_condition_line_cost(self):
        """An applied condition spec contributes
        payload_base_cost + base_severity*condition_severity_unit_cost
            + base_duration_rounds*condition_duration_unit_cost.

        Default config: payload_base_cost=2, condition_severity_unit_cost=1,
        condition_duration_unit_cost=1.
        Spec: base_severity=2, base_duration_rounds=3.
        line_cost = 2 + 2*1 + 3*1 = 7.
        """
        cfg = get_technique_budget_config()
        cond_spec = AppliedConditionSpec(condition_id=9999, base_severity=2, base_duration_rounds=3)
        d = _design(intensity=0, control=0, applied_conditions=(cond_spec,))
        bd = price_design(d, config=cfg, budget=200)

        cond_lines = [line for line in bd.lines if line.dimension == "condition"]
        assert len(cond_lines) == 1, f"Expected 1 condition line, got {cond_lines}"
        expected_cost = (
            cfg.payload_base_cost
            + 2 * cfg.condition_severity_unit_cost
            + 3 * cfg.condition_duration_unit_cost
        )
        assert cond_lines[0].power_cost == expected_cost

    def test_capability_and_condition_together(self):
        """Both a capability grant and an applied condition produce separate lines,
        and the gross cost is their sum plus intensity + control lines."""
        cfg = get_technique_budget_config()
        cap_spec = CapabilityGrantSpec(capability_id=9999, base_value=2, intensity_multiplier=0.0)
        cond_spec = AppliedConditionSpec(condition_id=9999, base_severity=1, base_duration_rounds=2)
        d = _design(
            intensity=4,
            control=3,
            capability_grants=(cap_spec,),
            applied_conditions=(cond_spec,),
        )
        bd = price_design(d, config=cfg, budget=200)

        dimensions = [line.dimension for line in bd.lines]
        assert "capability" in dimensions
        assert "condition" in dimensions
        # gross = intensity + control + capability_line + condition_line
        intensity_cost = 4 * cfg.intensity_unit_cost
        control_cost = 3 * cfg.control_unit_cost
        cap_line_cost = cfg.payload_base_cost + 2 * cfg.capability_value_unit_cost
        cond_line_cost = (
            cfg.payload_base_cost
            + 1 * cfg.condition_severity_unit_cost
            + 2 * cfg.condition_duration_unit_cost
        )
        assert bd.gross_cost == intensity_cost + control_cost + cap_line_cost + cond_line_cost
