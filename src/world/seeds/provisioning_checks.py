"""Cooking tradeskill check-ladder content (#2852, trimmed by #3006).

Activates the built-and-wired crafting engine's check spine for provisioning:
the Cooking skill (+ Brewing specialization) and its CheckType (wits +
Cooking), the live QualityTier ladder (the 12-rung #2878 ladder,
Poor→Legendary; quality tiers previously existed only in test factories)
plus the 7-rung AccentLevel ladder. Quality matters downstream: the event
catering loop (#2852) sums quality multipliers into host prestige — rich
preparations are the money sink and the grandeur.

``_ensure_cooking_check()`` and ``_ensure_quality_tiers()`` are the load-bearing
halves lore-repo ITEM_CREATE recipe fixtures FK by natural key (the "Cooking"
CheckType, the QualityTier ladder), so their pre-content home is now
``world.seeds.config_prerequisites.CONFIG_PREREQUISITES["provisioning"]`` (#3006
Task 5) — that entry runs BEFORE ``load_world_content()``, ahead of the
`seed_provisioning_content()` call below, which still calls both (idempotent) so
existing callers/tests of the cluster entry keep working.

The four example ITEM_CREATE recipes this module used to seed directly
(Hearty Stew, Honeyed Wine, Dream Dust, Haze) — plus their ingredient
ItemTemplates and skill-cap ladders — moved to the lore repo (#3006):
``CraftingRecipe``/``CraftingSkillCap``/``CraftingMaterialRequirement`` are
now ``CONTENT_MODELS`` (natural-keyed, #3006 Task 1), so a seeder minting
them directly would violate the #2698 "seeders never write content" rule
(see ``world.seeds.tests.test_no_content_slop``). Recipes are authored
content now; this module only ensures the check/skill/quality-ladder
machinery they roll against.

Mirrors ``social_checks.py``: skills/traits/checktypes are content-repo-owned
(#2698), looked up via ``authored_or_sample``; magnitudes PLACEHOLDER.
"""

from __future__ import annotations

from decimal import Decimal

COOKING_SKILL_NAME = "Cooking"
COOKING_CHECK_NAME = "Cooking"
BREWING_SPECIALIZATION_NAME = "Brewing"

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
    """Seed the Cooking check spine + quality/accent ladders (idempotent).

    Recipes that roll this check are authored content now (#3006) — this
    only ensures the machinery they depend on exists.
    """
    _ensure_cooking_check()
    _ensure_quality_tiers()


def _ensure_cooking_check():
    """The Cooking CheckType (wits + Cooking skill), content-owned rows."""
    from world.checks.models import (  # noqa: PLC0415
        CheckCategory,
        CheckType,
        CheckTypeSpecialization,
        CheckTypeTrait,
    )
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
    brewing = None
    if skill is not None:
        brewing, _created = Specialization.objects.get_or_create(
            parent_skill=skill,
            name=BREWING_SPECIALIZATION_NAME,
            defaults={"display_order": 0, "is_active": True},
        )
    wits = authored_or_sample(
        Trait,
        {"trait_type": TraitType.STAT, "category": TraitCategory.MENTAL, "is_public": True},
        name="wits",
    )
    agility = authored_or_sample(
        Trait,
        {"trait_type": TraitType.STAT, "category": TraitCategory.PHYSICAL, "is_public": True},
        name="agility",
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
    # Brewing rides the check as an authored specialization row (#2894 — the
    # Specialization existed but was never linked, so it contributed nothing).
    # Weight 1.0: spec is fully additive with the skill (Apostate: 50+50 ≡ 100).
    if brewing is not None:
        CheckTypeSpecialization.objects.get_or_create(
            check_type=check_type,
            specialization=brewing,
            defaults={"weight": Decimal("1.00")},
        )
    # Stat side = the AVERAGE of wits and agility (#2886, Apostate — echoing
    # Arx 1's higher-of-wits-and-dex; the average is what weighted rows can
    # express). update_or_create so the pre-ruling wits-0.50 rows retune.
    for stat in (wits, agility):
        if stat is not None:
            CheckTypeTrait.objects.update_or_create(
                check_type=check_type, trait=stat, defaults={"weight": Decimal("0.25")}
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
