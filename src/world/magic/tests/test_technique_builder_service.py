from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.exceptions import TechniqueBudgetExceeded
from world.magic.factories import (
    CharacterGiftFactory,
    EffectTypeFactory,
    GiftFactory,
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
from world.magic.types.technique_builder import DamageProfileSpec, TechniqueDesignInput


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
