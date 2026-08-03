"""Generic crafting-material ladders (#2878 Phase F — the ungated import core).

The curated Arx 1 import's uncontroversial base: the generic per-category
quality ladders (low/common/mid/high/exotic) that ~90% of Arx 1's 459
recipes actually consumed. Named canon materials (alaricite, steelsilk, …)
are deliberately ABSENT here — they land only after Apostate's row-by-row
keep/rename/drop worksheet. Gemstones are excluded wholesale (the built gem
economy owns stones); Arx 1's drug herbs are excluded (natively replaced by
the #2862 Dust & Haze botanicals).

``value`` carries Arx 1's price ladder (economy pricing); ``material_grade``
is the #2878 quality-score head start — materials are potential, never
performance (grades PLACEHOLDER, admin-tunable). Idempotent upserts.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# (category, name, value, material_grade) — value = Arx 1 ladder; grade PLACEHOLDER.
_MATERIALS = (
    ("Leather", "Low Quality Pelt", 1, 0),
    ("Leather", "Common Pelt", 30, 5),
    ("Leather", "Kid Leather", 50, 8),
    ("Leather", "High Quality Pelt", 625, 15),
    ("Leather", "Exotic Pelt", 6250, 25),
    ("Textiles", "Low Quality Cloth", 1, 0),
    ("Textiles", "Common Cloth", 20, 5),
    ("Textiles", "Felt", 20, 5),
    ("Textiles", "Satin", 20, 5),
    ("Textiles", "Lace", 50, 8),
    ("Textiles", "Silk", 625, 15),
    ("Metal", "Low Quality Metal", 1, 0),
    ("Metal", "Standard Steel", 30, 5),
    ("Metal", "High Quality Steel", 625, 15),
    ("Wood", "Low Quality Wood", 1, 0),
    ("Wood", "Wood", 125, 8),
    ("Ornaments", "Feather", 1, 0),
    ("Ornaments", "Bone", 1, 0),
    ("Ornaments", "Glass", 20, 5),
    ("Ornaments", "Semiprecious Metal", 625, 15),
    ("Ornaments", "Precious Metal", 1250, 18),
)

_CATEGORY_ORDER = ("Metal", "Textiles", "Leather", "Wood", "Ornaments")


def seed_crafting_materials() -> None:
    """Upsert the generic material categories + ladder templates (#2878)."""
    from world.items.models import ItemTemplate, MaterialCategory  # noqa: PLC0415

    categories = {}
    for order, name in enumerate(_CATEGORY_ORDER):
        category, _created = MaterialCategory.objects.update_or_create(
            name=name,
            defaults={
                "description": f"PLACEHOLDER: {name.lower()} crafting stock.",
                "sort_order": order,
            },
        )
        categories[name] = category

    for category_name, name, value, grade in _MATERIALS:
        ItemTemplate.objects.update_or_create(
            name=name,
            defaults={
                "description": f"PLACEHOLDER: {name.lower()} — crafting material.",
                "is_active": True,
                "value": value,
                "material_category": categories[category_name],
                "material_grade": grade,
            },
        )
    logger.info(
        "Seeded %s material categories and %s generic material templates.",
        len(categories),
        len(_MATERIALS),
    )
    seed_accent_axes()
    seed_craft_skills()


# The ratified accent vocabulary (#2886, Apostate 2026-08-02): seven axes.
# (name, adjective, check_type_name or None). Unwired axes stay authored-but-
# dormant — flagged skill-list holes (crowd-blending, courtly command), never
# force-fit. Regal spans a check family; the check-scoped seam is 1:1, so it
# stays dormant until the courtly CheckTypes land (design note on #2886).
_ACCENT_AXES = (
    ("allure", "alluring", None),  # attraction reads wire via npc_services, not a CheckType
    ("menace", "menacing", "Intimidation"),
    ("regal", "regal", None),
    ("dramatic", "dramatic", "Performance"),
    ("stealthy", "stealthy", "Stealth"),
    ("unassuming", "unassuming", None),
    ("nimble", "nimble", None),  # minor dodge touch — wire when a defense CheckType exists
)

#: Symmetric accent oppositions (#2886): Dramatic ⊥ Unassuming.
_ACCENT_EXCLUSIONS = (("dramatic", "unassuming"),)

# The ratified archetype matrix (Apostate 2026-08-02): function accents are
# garment-only (except unassuming plate — bland enough to get lost in a
# crowd); presence accents span everything worn including jewelry; menace
# touches weapons and jewelry (spiked torcs); regal weapons are ornate.
_GARMENTS = ("clothing", "robe", "light_armor")
_ALL_ARMOR = ("light_armor", "medium_armor", "heavy_armor")
_WORN = ("clothing", "robe", "jewelry", *_ALL_ARMOR)
_WEAPONS = ("melee_one_hand", "melee_two_hand", "ranged", "thrown", "shield", "lance")
_ACCENT_ARCHETYPES = {
    "allure": _WORN,
    "menace": (*_WORN, *_WEAPONS),
    "regal": (*_WORN, *_WEAPONS),
    "dramatic": _WORN,
    "stealthy": _GARMENTS,
    "unassuming": ("clothing", "robe", *_ALL_ARMOR),
    "nimble": _GARMENTS,
}


def seed_accent_axes() -> None:
    """Mark the seven ratified accent axes styleable + author their grammar.

    ``mechanics.ModifierCategory``/``ModifierTarget`` are content-repo-owned —
    looked up via ``authored_or_sample`` (no-op without the category). Existing
    targets (allure, menace) are flagged in place; the rest are created with
    PLACEHOLDER descriptions. CheckType wiring is fill-if-found only.
    """
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.mechanics.models import ModifierCategory, ModifierTarget  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415

    category = authored_or_sample(ModifierCategory, {}, name="roll_modifier")
    if category is None:
        return
    targets: dict[str, ModifierTarget] = {}
    for name, adjective, check_name in _ACCENT_AXES:
        check_type = CheckType.objects.filter(name=check_name).first() if check_name else None
        target = authored_or_sample(
            ModifierTarget,
            {
                "category": category,
                "description": f"PLACEHOLDER: the {adjective} accent axis (#2886).",
                "target_check_type": check_type,
            },
            name=name,
        )
        if target is None:
            continue
        updates: list[str] = []
        if not target.is_styleable:
            target.is_styleable = True
            updates.append("is_styleable")
        if not target.styleable_adjective:
            target.styleable_adjective = adjective
            updates.append("styleable_adjective")
        if target.target_check_type_id is None and check_type is not None:
            target.target_check_type = check_type
            updates.append("target_check_type")
        if updates:
            target.save(update_fields=updates)
        targets[name] = target

    _ensure_accent_exclusions(targets)
    _ensure_accent_archetype_allowances(targets)


def _ensure_accent_archetype_allowances(targets: dict) -> None:
    """Upsert the ratified accent × archetype allowlist (#2886)."""
    from world.items.crafting.models import AccentArchetypeAllowance  # noqa: PLC0415

    for name, archetypes in _ACCENT_ARCHETYPES.items():
        target = targets.get(name)
        if target is None:
            continue
        for archetype in archetypes:
            AccentArchetypeAllowance.objects.get_or_create(target=target, gear_archetype=archetype)


def _ensure_accent_exclusions(targets: dict) -> None:
    """Upsert the symmetric opposition rows (#2886)."""
    from world.items.crafting.models import AccentExclusion  # noqa: PLC0415

    for name_a, name_b in _ACCENT_EXCLUSIONS:
        a, b = targets.get(name_a), targets.get(name_b)
        if a is None or b is None:
            continue
        exists = AccentExclusion.objects.filter(target_a=a, target_b=b).exists() or (
            AccentExclusion.objects.filter(target_a=b, target_b=a).exists()
        )
        if not exists:
            AccentExclusion.objects.create(target_a=a, target_b=b)


# The ratified craft-skill taxonomy (#2886, Apostate 2026-08-02) — professions
# organized for character identity, recipes typed by broad output kinds, never
# materials. Bows live under Weaponsmithing; leather armor under Armorsmithing
# (leather garments fall to Tailoring); Jewelcrafting spans metal AND gem;
# Carpentry also feeds house-building (a building-project contribution seam,
# future content); Alchemy is the discovery-minigame dream (mix-and-match
# component matrix → discoverable materials — its own future spec); Cooking
# (Brewing) already exists; drugs may roll Cooking OR Alchemy per recipe.
# (skill name, tooltip PLACEHOLDER, display_order)
_CRAFT_SKILLS = (
    ("Weaponsmithing", "Blades, hafts, and bows — every instrument of war.", 41),
    ("Armorsmithing", "Plate, mail, and hardened leather — everything that turns a blow.", 42),
    ("Jewelcrafting", "Metal and gem alike — rings, torcs, crowns, and settings.", 43),
    ("Tailoring", "Cloth and soft leather — finery to fieldwear.", 44),
    ("Carpentry", "Furniture, fittings, and the bones of houses.", 45),
    ("Alchemy", "Components mixed toward discovery — remedies, poisons, and stranger things.", 46),
    ("Artistry", "Painting, sculpture, and works that exist to be seen.", 47),
)


def seed_craft_skills() -> None:
    """Seed the ratified crafting skills + one PLACEHOLDER CheckType each.

    Mirrors the Cooking pattern: content-owned rows via ``authored_or_sample``
    (no-ops without the authored spine). Stat side per Apostate's ruling
    (2026-08-02, echoing Arx 1's higher-of-wits-and-dex): the AVERAGE of wits
    and agility — wits 0.25 + agility 0.25, the same total stat share as a
    single stat at 0.50, expressible with the existing weighted-trait rows
    (higher-of would need a new mechanism). Skill 1.00.
    """
    from decimal import Decimal  # noqa: PLC0415

    from world.checks.models import CheckCategory, CheckType, CheckTypeTrait  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415
    from world.skills.models import Skill  # noqa: PLC0415
    from world.traits.models import Trait, TraitCategory, TraitType  # noqa: PLC0415

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
        return
    for name, tooltip, order in _CRAFT_SKILLS:
        skill_trait = authored_or_sample(
            Trait,
            {"trait_type": TraitType.SKILL, "category": TraitCategory.CRAFTING, "is_public": True},
            name=name,
        )
        if skill_trait is None:
            continue
        authored_or_sample(
            Skill,
            {"tooltip": f"PLACEHOLDER: {tooltip}", "display_order": order, "is_active": True},
            trait=skill_trait,
        )
        check_type = authored_or_sample(
            CheckType,
            {
                "category": category,
                "description": f"PLACEHOLDER: the {name} craft check.",
            },
            name=name,
        )
        if check_type is None:
            continue
        CheckTypeTrait.objects.get_or_create(
            check_type=check_type, trait=skill_trait, defaults={"weight": Decimal("1.00")}
        )
        for stat in (wits, agility):
            if stat is not None:
                CheckTypeTrait.objects.update_or_create(
                    check_type=check_type, trait=stat, defaults={"weight": Decimal("0.25")}
                )
