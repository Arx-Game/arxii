"""Cooking tradeskill + food/drink crafting content (#2852).

Activates the built-and-wired crafting engine for provisioning: the Cooking
skill (+ Brewing specialization) and its CheckType (wits + Cooking), the
first LIVE QualityTier ladder (Common/Fine/Masterwork previously existed only
in test factories), example ITEM_CREATE recipes (Hearty Stew, Honeyed Wine —
``requires_station=False``: kitchens, not labs), ingredient templates, and
skill-cap ladders so output quality clamps to the cook's skill. Quality
matters downstream: the event catering loop (#2852) sums quality multipliers
into host prestige — rich preparations are the money sink and the grandeur.

Mirrors ``social_checks.py``: skills/traits/checktypes are content-repo-owned
(#2698), looked up via ``authored_or_sample``; magnitudes PLACEHOLDER.
"""

from __future__ import annotations

from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

COOKING_SKILL_NAME = "Cooking"
COOKING_CHECK_NAME = "Cooking"
BREWING_SPECIALIZATION_NAME = "Brewing"

# (output template name, ((ingredient template name, quantity), ...))
_RECIPE_ROWS = (
    ("Hearty Stew", (("Sack of Grain", 1), ("Wild Herbs", 1))),
    ("Honeyed Wine", (("Orchard Honey", 2),)),
)

# (tier name, numeric_min, numeric_max, stat_multiplier, sort_order)
_QUALITY_TIERS = (
    ("Common", 0, 29, "1.00", 0),
    ("Fine", 30, 69, "1.25", 1),
    ("Masterwork", 70, 9999, "1.60", 2),
)
# (min skill value, tier name) — the cook's skill caps output quality.
_SKILL_CAP_LADDER = ((0, "Common"), (40, "Fine"), (80, "Masterwork"))


def seed_provisioning_content() -> None:
    """Seed the Cooking tradeskill + food/drink recipes (idempotent)."""
    from world.seeds.game_content.items import seed_consumable_catalog  # noqa: PLC0415

    seed_consumable_catalog()  # output templates must exist regardless of cluster order
    check_type = _ensure_cooking_check()
    tiers = _ensure_quality_tiers()
    if check_type is None:
        logger.warning("Cooking check unavailable (unauthored Trait/Skill); recipes skipped.")
        return
    _ensure_recipes(check_type, tiers)


def _ensure_cooking_check():
    """The Cooking CheckType (wits + Cooking skill), content-owned rows."""
    from world.checks.models import CheckCategory, CheckType, CheckTypeTrait  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415
    from world.skills.models import Skill, Specialization  # noqa: PLC0415
    from world.traits.models import Trait, TraitCategory, TraitType  # noqa: PLC0415

    skill_trait = authored_or_sample(
        Trait,
        {"trait_type": TraitType.SKILL, "category": TraitCategory.CRAFTING, "is_public": True},
        name=COOKING_SKILL_NAME,
    )
    if skill_trait is None:
        return None
    skill = authored_or_sample(
        Skill,
        {
            "tooltip": "The table as craft — food, drink, and the art of provision.",
            "display_order": 40,
            "is_active": True,
        },
        trait=skill_trait,
    )
    if skill is not None:
        Specialization.objects.get_or_create(
            parent_skill=skill,
            name=BREWING_SPECIALIZATION_NAME,
            defaults={"display_order": 0, "is_active": True},
        )
    wits = authored_or_sample(
        Trait,
        {"trait_type": TraitType.STAT, "category": TraitCategory.MENTAL, "is_public": True},
        name="wits",
    )
    category = authored_or_sample(
        CheckCategory,
        {"description": "Trade and craft checks.", "display_order": 40},
        name="Crafting",
    )
    if category is None:
        return None
    check_type = authored_or_sample(
        CheckType,
        {"category": category, "description": "Preparing food and drink worth serving."},
        name=COOKING_CHECK_NAME,
    )
    if check_type is None:
        return None
    CheckTypeTrait.objects.get_or_create(
        check_type=check_type, trait=skill_trait, defaults={"weight": Decimal("1.00")}
    )
    if wits is not None:
        CheckTypeTrait.objects.get_or_create(
            check_type=check_type, trait=wits, defaults={"weight": Decimal("0.50")}
        )
    return check_type


def _ensure_quality_tiers() -> dict[str, object]:
    """The first live QualityTier ladder (test-factory values promoted)."""
    from world.items.models import QualityTier  # noqa: PLC0415

    tiers: dict[str, object] = {}
    for name, low, high, multiplier, order in _QUALITY_TIERS:
        tier, _created = QualityTier.objects.get_or_create(
            name=name,
            defaults={
                "numeric_min": low,
                "numeric_max": high,
                "stat_multiplier": Decimal(multiplier),
                "sort_order": order,
            },
        )
        tiers[name] = tier
    return tiers


def _ensure_recipes(check_type, tiers: dict[str, object]) -> None:
    """The example ITEM_CREATE recipes + ingredients + skill caps."""
    from world.items.crafting.constants import CraftingRecipeKind  # noqa: PLC0415
    from world.items.crafting.models import (  # noqa: PLC0415
        CraftingMaterialRequirement,
        CraftingRecipe,
        CraftingSkillCap,
    )
    from world.items.models import ItemTemplate  # noqa: PLC0415
    from world.traits.models import Trait, TraitType  # noqa: PLC0415

    skill_trait = Trait.objects.filter(name=COOKING_SKILL_NAME, trait_type=TraitType.SKILL).first()
    for output_name, ingredients in _RECIPE_ROWS:
        output = ItemTemplate.objects.filter(name=output_name).first()
        if output is None:
            logger.warning("Recipe output template %r missing; recipe skipped.", output_name)
            continue
        recipe, _created = CraftingRecipe.objects.get_or_create(
            kind=CraftingRecipeKind.ITEM_CREATE,
            output_item_template=output,
            defaults={
                "name": f"Cook: {output_name}",
                "check_type": check_type,
                "skill_trait": skill_trait,
                "base_difficulty": 10,
                "success_level_step": 10,
                "min_success_level": 1,
                "action_point_cost": 2,
                "requires_station": False,
            },
        )
        for ingredient_name, quantity in ingredients:
            ingredient, _created = ItemTemplate.objects.get_or_create(
                name=ingredient_name,
                defaults={
                    "description": f"PLACEHOLDER: {ingredient_name.lower()} — cooking stock.",
                    "is_active": True,
                },
            )
            CraftingMaterialRequirement.objects.get_or_create(
                recipe=recipe,
                item_template=ingredient,
                defaults={"quantity": quantity},
            )
        for min_skill, tier_name in _SKILL_CAP_LADDER:
            tier = tiers.get(tier_name)
            if tier is None:
                continue
            CraftingSkillCap.objects.get_or_create(
                recipe=recipe,
                min_skill_value=min_skill,
                defaults={"max_quality_tier": tier},
            )
