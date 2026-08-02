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
