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
