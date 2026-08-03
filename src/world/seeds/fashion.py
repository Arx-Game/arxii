"""Fashion vocabulary starter content (#2907).

Seeds the Silhouette form catalog (umbrella hierarchy: boot -> thigh-high
boot) and a starter set of cultural/historical Styles. ALL names and
descriptions here are PLACEHOLDER pending Apostate's lore pass — rows are
admin-editable content, seeded with ``update_or_create`` on name so edits to
non-key fields survive re-seeds only where we don't re-assert them (family
and hierarchy are re-asserted; descriptions are set only on create).

The vocabulary is deliberately additive-cost: |silhouettes| + |styles|, never
a matrix — combinations happen at the workbench (see the #2907 design
capture).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# (name, wear_family, parent name or None) — umbrellas first so parents resolve.
# PLACEHOLDER starter forms; the list grows under player pressure (and, later,
# icon-founded additions).
_SILHOUETTES: tuple[tuple[str, str, str | None], ...] = (
    # Footwear
    ("Boot", "footwear", None),
    ("Thigh-High Boot", "footwear", "Boot"),
    ("Ankle Boot", "footwear", "Boot"),
    ("Riding Boot", "footwear", "Boot"),
    ("Shoe", "footwear", None),
    ("Slipper", "footwear", "Shoe"),
    ("Stiletto Heel", "footwear", "Shoe"),
    ("Sandal", "footwear", "Shoe"),
    # Legwear
    ("Trousers", "legwear", None),
    ("Breeches", "legwear", "Trousers"),
    ("Hose", "legwear", "Trousers"),
    ("Skirt", "legwear", None),
    ("Full Skirt", "legwear", "Skirt"),
    ("Split Skirt", "legwear", "Skirt"),
    # Torso garments
    ("Bodice", "torso_garment", None),
    ("Corset", "torso_garment", "Bodice"),
    ("Shirt", "torso_garment", None),
    ("Blouse", "torso_garment", "Shirt"),
    ("Tunic", "torso_garment", "Shirt"),
    ("Doublet", "torso_garment", None),
    ("Jerkin", "torso_garment", "Doublet"),
    # Full garments
    ("Gown", "full_garment", None),
    ("Sheath Gown", "full_garment", "Gown"),
    ("Ballgown", "full_garment", "Gown"),
    ("Robe", "full_garment", None),
    # Outerwear
    ("Cloak", "outerwear", None),
    ("Capelet", "outerwear", "Cloak"),
    ("Greatcloak", "outerwear", "Cloak"),
    ("Coat", "outerwear", None),
    ("Longcoat", "outerwear", "Coat"),
    # Headwear
    ("Hat", "headwear", None),
    ("Wide-Brim Hat", "headwear", "Hat"),
    ("Circlet", "headwear", None),
    ("Veil", "headwear", None),
    # Handwear
    ("Gloves", "handwear", None),
    ("Lace Gloves", "handwear", "Gloves"),
    ("Gauntlets", "handwear", "Gloves"),
    # Jewelry
    ("Ring", "jewelry", None),
    ("Signet Ring", "jewelry", "Ring"),
    ("Necklace", "jewelry", None),
    ("Choker", "jewelry", "Necklace"),
    ("Pendant Chain", "jewelry", "Necklace"),
    ("Earring", "jewelry", None),
    ("Drop Earring", "jewelry", "Earring"),
    ("Bracelet", "jewelry", None),
    ("Brooch", "jewelry", None),
    # Accessories
    ("Sash", "accessory", None),
    ("Belt", "accessory", None),
    ("Fan", "accessory", None),
)

# (name, origin, era) — cultural/historical registers ONLY (#2907: intent
# adjectives are Accent-redundant and rejected at authoring). Names/origins
# are PLACEHOLDER stand-ins for the real regional cultures.
_STYLES: tuple[tuple[str, str, str], ...] = (
    ("Arxian Court", "Arx (PLACEHOLDER)", "current"),
    ("Highland Weave", "Northern highlands (PLACEHOLDER)", "current"),
    ("Coastal Flow", "Southern coasts (PLACEHOLDER)", "current"),
    ("Riverlands Practical", "Riverlands (PLACEHOLDER)", "current"),
    ("Steppe Rider", "Eastern steppes (PLACEHOLDER)", "current"),
    ("Desert Veil", "Far-south deserts (PLACEHOLDER)", "current"),
    # Ancient registers — dead languages of dress; not in any starting
    # knowledge, rediscovered through investigation. Arx holds a wide spread.
    ("Old-Regime", "The regime before the current order (PLACEHOLDER)", "ancient"),
    ("Dawn Empire", "A fallen empire of the deep past (PLACEHOLDER)", "ancient"),
    ("Shrouded Era", "An age remembered mostly in fragments (PLACEHOLDER)", "ancient"),
)


def seed_fashion_vocabulary() -> None:
    """Seed silhouettes + cultural styles (idempotent)."""
    from world.items.models import Silhouette, Style  # noqa: PLC0415

    by_name: dict[str, Silhouette] = {}
    for name, family, parent_name in _SILHOUETTES:
        parent = by_name.get(parent_name) if parent_name else None
        row, created = Silhouette.objects.update_or_create(
            name=name,
            defaults={"wear_family": family, "parent": parent, "is_active": True},
        )
        if created and not row.description:
            row.description = f"PLACEHOLDER — describe the {name.lower()} form."
            row.save(update_fields=["description"])
        by_name[name] = row

    for name, origin, era in _STYLES:
        style, created = Style.objects.update_or_create(
            name=name,
            defaults={"era": era},
        )
        if created:
            style.origin = origin
            style.description = f"PLACEHOLDER — the {name} register of dress."
            style.save(update_fields=["origin", "description"])
    logger.info(
        "Fashion vocabulary seeded: %d silhouettes, %d styles.",
        len(_SILHOUETTES),
        len(_STYLES),
    )
