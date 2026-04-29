"""Items test-infrastructure: seed helpers for ItemTemplate + compatibility matrix.

Exports:
- ``seed_item_template_starter_catalog()`` — reference ItemTemplates per gear_archetype
- ``seed_gear_archetype_compatibility()`` — canonical role × archetype compatibility matrix
- ``seed_items_dev()`` — master orchestrator for the items cluster
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.covenants.models import CovenantRole, GearArchetypeCompatibility
    from world.items.models import ItemTemplate


@dataclass
class ItemTemplateStarterCatalogResult:
    """Returned by seed_item_template_starter_catalog()."""

    templates: dict[str, ItemTemplate]  # GearArchetype value → template


@dataclass
class GearArchetypeCompatibilityResult:
    """Returned by seed_gear_archetype_compatibility()."""

    compatibilities: list[GearArchetypeCompatibility]
    sword_role: CovenantRole
    shield_role: CovenantRole
    crown_role: CovenantRole


@dataclass
class ItemsDevSeedResult:
    """Returned by seed_items_dev()."""

    template_catalog: ItemTemplateStarterCatalogResult
    compatibility: GearArchetypeCompatibilityResult


# ---------------------------------------------------------------------------
# Template specs: (archetype, name, [(body_region, equipment_layer)], facet_capacity)
# Layers: BASE = form-fitting base garment/armour layer.
#         OVER  = outer piece worn over base.
#         OUTER = outermost (cloaks, coats, full plate surcoat).
# ---------------------------------------------------------------------------

_TEMPLATE_SPECS: list[tuple[str, str, list[tuple[str, str]], int]] = []
# populated lazily below so we can reference the constants at call time


def _build_template_specs() -> list[tuple[str, str, list[tuple[str, str]], int]]:
    """Return the canonical template-spec list using actual constant values."""
    from world.items.constants import BodyRegion, EquipmentLayer, GearArchetype  # noqa: PLC0415

    return [
        (
            GearArchetype.HEAVY_ARMOR,
            "Plate Cuirass",
            [(BodyRegion.TORSO, EquipmentLayer.OVER)],
            3,
        ),
        (
            GearArchetype.MEDIUM_ARMOR,
            "Brigandine Vest",
            [(BodyRegion.TORSO, EquipmentLayer.BASE)],
            3,
        ),
        (
            GearArchetype.LIGHT_ARMOR,
            "Studded Leather Jacket",
            [(BodyRegion.TORSO, EquipmentLayer.BASE)],
            3,
        ),
        (
            GearArchetype.ROBE,
            "Scholar Robe",
            [
                (BodyRegion.TORSO, EquipmentLayer.BASE),
                (BodyRegion.LEFT_ARM, EquipmentLayer.BASE),
                (BodyRegion.RIGHT_ARM, EquipmentLayer.BASE),
            ],
            4,
        ),
        (
            GearArchetype.MELEE_ONE_HAND,
            "Longsword",
            [(BodyRegion.RIGHT_HAND, EquipmentLayer.BASE)],
            2,
        ),
        (
            GearArchetype.MELEE_TWO_HAND,
            "Greatsword",
            [
                (BodyRegion.RIGHT_HAND, EquipmentLayer.BASE),
                (BodyRegion.LEFT_HAND, EquipmentLayer.BASE),
            ],
            2,
        ),
        (
            GearArchetype.SHIELD,
            "Kite Shield",
            [(BodyRegion.LEFT_HAND, EquipmentLayer.BASE)],
            2,
        ),
        (
            GearArchetype.CLOTHING,
            "Fine Linen Shirt",
            [(BodyRegion.TORSO, EquipmentLayer.BASE)],
            2,
        ),
        (
            GearArchetype.JEWELRY,
            "Silver Pendant",
            [(BodyRegion.NECK, EquipmentLayer.ACCESSORY)],
            2,
        ),
        (
            GearArchetype.RANGED,
            "Recurve Bow",
            [
                (BodyRegion.RIGHT_HAND, EquipmentLayer.BASE),
                (BodyRegion.LEFT_HAND, EquipmentLayer.BASE),
            ],
            2,
        ),
    ]


def seed_item_template_starter_catalog() -> ItemTemplateStarterCatalogResult:
    """Author one reference ItemTemplate per major gear_archetype with TemplateSlot rows.

    Templates authored: heavy_armor, medium_armor, light_armor, robe,
    melee_one_hand, melee_two_hand, shield, clothing, jewelry, ranged.
    All idempotent via get_or_create on name.

    Returns:
        ItemTemplateStarterCatalogResult with archetype-value → template mapping.
    """
    from world.items.models import ItemTemplate, TemplateSlot  # noqa: PLC0415

    templates: dict[str, ItemTemplate] = {}
    for archetype, name, slot_specs, capacity in _build_template_specs():
        tmpl, _ = ItemTemplate.objects.get_or_create(
            name=name,
            defaults={
                "gear_archetype": archetype,
                "facet_capacity": capacity,
            },
        )
        for region, layer in slot_specs:
            TemplateSlot.objects.get_or_create(
                template=tmpl,
                body_region=region,
                equipment_layer=layer,
            )
        templates[archetype] = tmpl

    return ItemTemplateStarterCatalogResult(templates=templates)


# ---------------------------------------------------------------------------
# Compatibility matrix: canonical role × archetype pairs.
# ---------------------------------------------------------------------------


def seed_gear_archetype_compatibility() -> GearArchetypeCompatibilityResult:
    """Author the canonical role × archetype compatibility matrix.

    Roles authored (get_or_create on slug):
    - sword-vanguard  (SWORD archetype)
    - shield-bulwark  (SHIELD archetype)
    - crown-luminary  (CROWN archetype)

    Compatibility matrix:
    - Sword: heavy_armor, medium_armor, light_armor, melee_one_hand, melee_two_hand
    - Shield: heavy_armor, medium_armor, shield
    - Crown: robe, clothing, jewelry

    All idempotent via get_or_create on (covenant_role, gear_archetype).

    Returns:
        GearArchetypeCompatibilityResult with all compat rows + role instances.
    """
    from world.covenants.constants import CovenantType, RoleArchetype  # noqa: PLC0415
    from world.covenants.models import CovenantRole, GearArchetypeCompatibility  # noqa: PLC0415
    from world.items.constants import GearArchetype  # noqa: PLC0415

    sword_role, _ = CovenantRole.objects.get_or_create(
        slug="sword-vanguard",
        defaults={
            "name": "Vanguard",
            "covenant_type": CovenantType.DURANCE,
            "archetype": RoleArchetype.SWORD,
            "speed_rank": 2,
        },
    )
    shield_role, _ = CovenantRole.objects.get_or_create(
        slug="shield-bulwark",
        defaults={
            "name": "Bulwark",
            "covenant_type": CovenantType.DURANCE,
            "archetype": RoleArchetype.SHIELD,
            "speed_rank": 3,
        },
    )
    crown_role, _ = CovenantRole.objects.get_or_create(
        slug="crown-luminary",
        defaults={
            "name": "Luminary",
            "covenant_type": CovenantType.DURANCE,
            "archetype": RoleArchetype.CROWN,
            "speed_rank": 1,
        },
    )

    matrix: list[tuple[CovenantRole, str]] = [
        # Sword — offense; works with all armour weights and both melee archetypes
        (sword_role, GearArchetype.HEAVY_ARMOR),
        (sword_role, GearArchetype.MEDIUM_ARMOR),
        (sword_role, GearArchetype.LIGHT_ARMOR),
        (sword_role, GearArchetype.MELEE_ONE_HAND),
        (sword_role, GearArchetype.MELEE_TWO_HAND),
        # Shield — defense; heavy/medium armour + shield archetype
        (shield_role, GearArchetype.HEAVY_ARMOR),
        (shield_role, GearArchetype.MEDIUM_ARMOR),
        (shield_role, GearArchetype.SHIELD),
        # Crown — support; robes, clothing, jewelry
        (crown_role, GearArchetype.ROBE),
        (crown_role, GearArchetype.CLOTHING),
        (crown_role, GearArchetype.JEWELRY),
    ]

    compats: list[GearArchetypeCompatibility] = [
        GearArchetypeCompatibility.objects.get_or_create(
            covenant_role=role,
            gear_archetype=archetype,
        )[0]
        for role, archetype in matrix
    ]

    return GearArchetypeCompatibilityResult(
        compatibilities=compats,
        sword_role=sword_role,
        shield_role=shield_role,
        crown_role=crown_role,
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def seed_items_dev() -> ItemsDevSeedResult:
    """Seed the entire items cluster in one idempotent call.

    Composes:
    1. ``seed_item_template_starter_catalog()`` — one reference template per
       major gear_archetype with TemplateSlot rows.
    2. ``seed_gear_archetype_compatibility()`` — canonical covenant role rows +
       role × archetype compatibility matrix.

    All writes are idempotent (get_or_create throughout). Re-running on a
    populated database is a no-op; staff edits to existing rows are preserved.

    Returns:
        ItemsDevSeedResult composing all sub-results.
    """
    template_catalog = seed_item_template_starter_catalog()
    compatibility = seed_gear_archetype_compatibility()
    return ItemsDevSeedResult(
        template_catalog=template_catalog,
        compatibility=compatibility,
    )
