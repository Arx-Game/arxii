"""Cooking tradeskill + food/drink crafting content (#2852).

Activates the built-and-wired crafting engine for provisioning: the Cooking
skill (+ Brewing specialization) and its CheckType (wits + Cooking), the
live QualityTier ladder (the 12-rung #2878 ladder, Poor→Legendary; quality
tiers previously existed only in test factories) plus the 7-rung AccentLevel
ladder, example ITEM_CREATE recipes (Hearty Stew, Honeyed Wine —
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

# Recipes exercising a specialization (#2886 — spec is additive with the
# skill on the roll AND the quality cap; Apostate: 50+50 ≡ 100).
_RECIPE_SPECIALIZATIONS = {"Honeyed Wine": BREWING_SPECIALIZATION_NAME}

# (output template name, ((ingredient template name, quantity), ...), workshop_gated)
_RECIPE_ROWS = (
    ("Hearty Stew", (("Sack of Grain", 1), ("Wild Herbs", 1)), False),
    ("Honeyed Wine", (("Orchard Honey", 2),), False),
    # #2862 — illicit refinement, gated on the Workshop of Iniquity. Rolls the
    # Cooking check as PLACEHOLDER (a dedicated refining skill is a flagged
    # skill-list hole, not force-fit).
    ("Dream Dust", (("Duskpetal Resin", 2),), True),
    ("Haze", (("Hazeleaf", 2),), True),
)

# MaterialCategory content (#2862) — the model has existed contentless since #684.
_MATERIAL_CATEGORIES = (
    ("Botanical", "Herbs, resins, and leaves — culinary or contraband."),
    ("Provision", "Grains, honeys, and stock for the table."),
)
_INGREDIENT_CATEGORY = {
    "Sack of Grain": "Provision",
    "Wild Herbs": "Botanical",
    "Orchard Honey": "Provision",
    "Duskpetal Resin": "Botanical",
    "Hazeleaf": "Botanical",
}

# The 12-rung quality ladder (#2878). Rung = sort_order; 1-9 are mundane-
# reachable (Arx 1's adjectives, PLACEHOLDER names pending Apostate's rename
# pass — rows are admin-editable), 10 divine / 11 transcendent / 12 legendary
# are thread-gated (see crafting.constants.BASE_MAX_QUALITY_RUNG). Bands and
# multipliers are PLACEHOLDER tuning.
# (tier name, numeric_min, numeric_max, stat_multiplier, sort_order, color_hex)
_QUALITY_TIERS = (
    ("Poor", 0, 9, "0.80", 1, "#9E9E9E"),
    ("Mediocre", 10, 19, "0.90", 2, "#B0BEC5"),
    ("Average", 20, 29, "1.00", 3, "#E0E0E0"),
    ("Above Average", 30, 39, "1.05", 4, "#C8E6C9"),
    ("Well-Crafted", 40, 49, "1.10", 5, "#A5D6A7"),
    ("Fine", 50, 59, "1.20", 6, "#66BB6A"),
    ("Exceptional", 60, 69, "1.30", 7, "#42A5F5"),
    ("Superb", 70, 79, "1.45", 8, "#7E57C2"),
    ("Perfect", 80, 99, "1.60", 9, "#AB47BC"),
    ("Divine", 100, 119, "1.80", 10, "#FFD54F"),
    ("Transcendent", 120, 149, "2.00", 11, "#FF8A65"),
    ("Legendary", 150, 9999, "2.30", 12, "#FF5252"),
)
#: The 3-row placeholder ladder this 12-rung ladder replaces; deleted on seed.
_LEGACY_TIER_NAMES = ("Common", "Masterwork")
# (min skill value, tier name) — the cook's skill caps output quality.
# Retuned for the 12-rung ladder (#2886): caps sit ~1-2 rungs above a
# crafter's typical score so a hot roll can genuinely punch upward (the
# "wow" outcome, Apostate's ruling 2026-08-02) while a novice with great
# materials still squanders them. Trait values are the internal ×10 scale
# (player-facing 3.0 = 30). PLACEHOLDER tuning.
_SKILL_CAP_LADDER = (
    (0, "Well-Crafted"),
    (20, "Fine"),
    (30, "Exceptional"),
    (40, "Superb"),
    (55, "Perfect"),
)

# The benefit-only Accent ladder (#2878): 7 adverbs, thread-gated past
# BASE_MAX_ACCENT_LEVEL. Content lands in the Accents phase; the ladder is
# seeded with the quality ladder because they are tuned together.
_ACCENT_LEVELS = (
    (1, "slightly"),
    (2, "modestly"),
    (3, "quite"),
    (4, "very"),
    (5, "extremely"),
    (6, "amazingly"),
    (7, "legendarily"),
)


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
    """The live 12-rung QualityTier ladder + the 7-rung Accent ladder (#2878).

    ``update_or_create`` (not get_or_create) so band/multiplier retunes land on
    re-seed, and so the legacy 3-row ladder's overlapping bands are corrected
    in place. Legacy rows whose names left the ladder are deleted (dev-only
    data; a ProtectedError would mean real crafted rows point at them — that
    aborts the seed loudly rather than leaving overlapping bands).
    """
    from world.items.models import AccentLevel, QualityTier  # noqa: PLC0415

    tiers: dict[str, object] = {}
    for name, low, high, multiplier, order, color in _QUALITY_TIERS:
        tier, _created = QualityTier.objects.update_or_create(
            name=name,
            defaults={
                "numeric_min": low,
                "numeric_max": high,
                "stat_multiplier": Decimal(multiplier),
                "sort_order": order,
                "color_hex": color,
            },
        )
        tiers[name] = tier
    QualityTier.objects.filter(name__in=_LEGACY_TIER_NAMES).delete()
    for level, name in _ACCENT_LEVELS:
        AccentLevel.objects.update_or_create(level=level, defaults={"name": name})
    return tiers


def _recipe_specialization(output_name: str):
    """The Specialization row a recipe exercises, or None (#2886)."""
    from world.skills.models import Specialization  # noqa: PLC0415

    spec_name = _RECIPE_SPECIALIZATIONS.get(output_name)
    if spec_name is None:
        return None
    return Specialization.objects.filter(name=spec_name).first()


def _ensure_recipes(check_type, tiers: dict[str, object]) -> None:
    """The example ITEM_CREATE recipes + ingredients + skill caps."""
    from world.items.crafting.constants import CraftingRecipeKind  # noqa: PLC0415
    from world.items.crafting.models import (  # noqa: PLC0415
        CraftingMaterialRequirement,
        CraftingRecipe,
        CraftingSkillCap,
    )
    from world.items.models import (  # noqa: PLC0415
        ItemTemplate,
        MaterialCategory,
    )
    from world.room_features.seeds import (  # noqa: PLC0415
        ensure_workshop_of_iniquity_kind,
    )
    from world.traits.models import Trait, TraitType  # noqa: PLC0415

    categories: dict[str, object] = {}
    for cat_name, cat_desc in _MATERIAL_CATEGORIES:
        category, _created = MaterialCategory.objects.get_or_create(
            name=cat_name, defaults={"description": cat_desc}
        )
        categories[cat_name] = category
    workshop_kind = ensure_workshop_of_iniquity_kind()
    skill_trait = Trait.objects.filter(name=COOKING_SKILL_NAME, trait_type=TraitType.SKILL).first()
    for output_name, ingredients, workshop_gated in _RECIPE_ROWS:
        output = ItemTemplate.objects.filter(name=output_name).first()
        if output is None:
            logger.warning("Recipe output template %r missing; recipe skipped.", output_name)
            continue
        verb = "Refine" if workshop_gated else "Cook"
        recipe, _created = CraftingRecipe.objects.get_or_create(
            kind=CraftingRecipeKind.ITEM_CREATE,
            output_item_template=output,
            defaults={
                "name": f"{verb}: {output_name}",
                "check_type": check_type,
                "skill_trait": skill_trait,
                "base_difficulty": 20 if workshop_gated else 10,
                "specialization": _recipe_specialization(output_name),
                "success_level_step": 10,
                "min_success_level": 1,
                "action_point_cost": 2,
                "requires_station": False,
                "required_feature_kind": workshop_kind if workshop_gated else None,
            },
        )
        for ingredient_name, quantity in ingredients:
            ingredient, _created = ItemTemplate.objects.get_or_create(
                name=ingredient_name,
                defaults={
                    "description": f"PLACEHOLDER: {ingredient_name.lower()} — cooking stock.",
                    "is_active": True,
                    "material_category": categories.get(
                        _INGREDIENT_CATEGORY.get(ingredient_name, ""),
                    ),
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
