"""Items test-infrastructure: seed helpers for ItemTemplate + style vocabulary.

Exports:
- ``seed_item_template_starter_catalog()`` — reference ItemTemplates per gear_archetype
- ``seed_style_vocabulary()`` — seeded ``Style`` aesthetic vocabulary spread across the
  audacity tiers (#2029)
- ``seed_items_dev()`` — master orchestrator for the items cluster

The canonical covenant-role × gear-archetype compatibility matrix (formerly
``seed_gear_archetype_compatibility()`` here, keyed on three placeholder
CovenantRole rows — ``sword-vanguard``/``shield-bulwark``/``crown-luminary``)
was retired: the 13 real Durance covenant vows are now lore-repo content
(``covenants.covenantrole``/``covenants.geararchetypecompatibility`` are
``CONTENT_MODELS``), and the placeholders collided with them on the
``(covenant_type, name)`` unique constraint. ``GearArchetypeCompatibility``
rows are authored in the lore repo now.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.items.models import ItemTemplate, Style


@dataclass
class ItemTemplateStarterCatalogResult:
    """Returned by seed_item_template_starter_catalog()."""

    templates: dict[str, ItemTemplate]  # GearArchetype value → template


@dataclass
class ItemsDevSeedResult:
    """Returned by seed_items_dev()."""

    template_catalog: ItemTemplateStarterCatalogResult
    styles: dict[str, Style]  # Style name -> row, keyed by the seeded vocabulary


# ---------------------------------------------------------------------------
# Template specs:
#   (archetype, name, [(body_region, equipment_layer)], facet_capacity, weapon_class)
# Layers: BASE = form-fitting base garment/armour layer.
#         OVER  = outer piece worn over base.
#         OUTER = outermost (cloaks, coats, full plate surcoat).
# weapon_class is a str | None: the WeaponClass row *name* to resolve, via
# seed_item_template_starter_catalog()'s weapon_classes lookup, to a model
# instance for the template's weapon_class FK. None for everything that
# isn't a weapon, and for weapons intentionally left unclassified (falling
# back to the coarse gear_archetype map). None is the field's blank
# sentinel now (nullable FK, #2879) — it was "" under the old CharField
# (#2858).
# ---------------------------------------------------------------------------


def _build_template_specs() -> list[tuple[str, str, list[tuple[str, str]], int, str | None]]:
    """Return the canonical template-spec list using actual constant values."""
    from world.items.constants import (  # noqa: PLC0415
        BodyRegion,
        EquipmentLayer,
        GearArchetype,
    )

    return [
        (
            GearArchetype.HEAVY_ARMOR,
            "Plate Cuirass",
            [(BodyRegion.TORSO, EquipmentLayer.OVER)],
            3,
            None,
        ),
        (
            GearArchetype.MEDIUM_ARMOR,
            "Brigandine Vest",
            [(BodyRegion.TORSO, EquipmentLayer.BASE)],
            3,
            None,
        ),
        (
            GearArchetype.LIGHT_ARMOR,
            "Studded Leather Jacket",
            [(BodyRegion.TORSO, EquipmentLayer.BASE)],
            3,
            None,
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
            None,
        ),
        (
            GearArchetype.MELEE_ONE_HAND,
            "Longsword",
            [(BodyRegion.RIGHT_HAND, EquipmentLayer.BASE)],
            2,
            "Balanced blade",
        ),
        (
            GearArchetype.MELEE_TWO_HAND,
            "Greatsword",
            [
                (BodyRegion.RIGHT_HAND, EquipmentLayer.BASE),
                (BodyRegion.LEFT_HAND, EquipmentLayer.BASE),
            ],
            2,
            "Heavy blade",
        ),
        (
            GearArchetype.SHIELD,
            "Kite Shield",
            [(BodyRegion.LEFT_HAND, EquipmentLayer.BASE)],
            2,
            None,
        ),
        (
            GearArchetype.CLOTHING,
            "Fine Linen Shirt",
            [(BodyRegion.TORSO, EquipmentLayer.BASE)],
            2,
            None,
        ),
        (
            GearArchetype.JEWELRY,
            "Silver Pendant",
            [(BodyRegion.NECK, EquipmentLayer.ACCESSORY)],
            2,
            None,
        ),
        (
            GearArchetype.RANGED,
            "Recurve Bow",
            [
                (BodyRegion.RIGHT_HAND, EquipmentLayer.BASE),
                (BodyRegion.LEFT_HAND, EquipmentLayer.BASE),
            ],
            2,
            "Hunting bow",
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
    from world.items.models import ItemTemplate, TemplateSlot, WeaponClass  # noqa: PLC0415

    weapon_classes = {
        "Balanced blade": {"strength_tenths": 5, "default_damage": 5},
        "Heavy blade": {"strength_tenths": 7, "default_damage": 7},
        "Hunting bow": {"strength_tenths": 5, "default_damage": 4},
    }
    weapon_class_rows: dict[str, WeaponClass] = {}
    for name, fields in weapon_classes.items():
        row, _ = WeaponClass.objects.get_or_create(name=name, defaults=fields)
        weapon_class_rows[name] = row

    templates: dict[str, ItemTemplate] = {}
    for archetype, name, slot_specs, capacity, weapon_class_name in _build_template_specs():
        tmpl, _ = ItemTemplate.objects.get_or_create(
            name=name,
            defaults={
                "gear_archetype": archetype,
                "facet_capacity": capacity,
                "weapon_class": weapon_class_rows.get(weapon_class_name)
                if weapon_class_name
                else None,
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
# Style vocabulary (#2029): seeded across the four StyleAudacity tiers so the
# audacity axis has real vocabulary to play with out of the box.
# ---------------------------------------------------------------------------

# name -> (audacity tier, description). Authoritative on reseed (update_or_create)
# so a tuning/wording tweak lands without row churn, mirroring seed_scandal_archetypes.
_STYLE_VOCABULARY: dict[str, tuple[int, str]] = {
    # UNDERSTATED — restrained, unassuming, easy to overlook.
    "Demure": (1, "Modest and reserved — eyes lowered, colors muted, nothing to draw a glance."),
    "Austere": (1, "Plain and unadorned by design — severity as a statement of restraint."),
    "Somber": (1, "Muted and grave — dark tones, no ornament, a mood worn as cloth."),
    "Prim": (1, "Fastidiously neat and correct — not a hair, hem, or seam out of place."),
    # EXPRESSIVE — a clear identity, worn with confidence but not spectacle.
    "Regal": (2, "Carries itself like it belongs to a throne room — dignity, not display."),
    "Rustic": (2, "Homespun and unpretentious — the honest craft of hearth and field."),
    "Scholarly": (2, "Ink-stained and bookish — the wardrobe of someone who reads for a living."),
    "Devout": (2, "Worn like a vow — the plain sincerity of faith rather than its pageantry."),
    # BOLD — deliberately eye-catching; a statement that invites attention.
    "Menacing": (3, "Cut to unsettle — sharp lines and dark intent worn as a warning."),
    "Flamboyant": (3, "Loud colors, bigger silhouettes — dressed to be seen across the room."),
    "Rakish": (3, "A calculated disarray — the confidence of someone who breaks the rules well."),
    "Opulent": (3, "Wealth worn without apology — the finest materials, unmissably so."),
    # OUTRAGEOUS — maximal daring; scandalizes as often as it dazzles.
    "Seductive": (4, "Cut and worn to court desire openly — nothing subtle about the intent."),
    "Scandalous": (4, "Courts gossip on sight — the outfit itself is the provocation."),
    "Predatory": (4, "Sharp, hungry, and unapologetic — dressed like the room's apex."),
    "Resplendent": (
        4,
        "Blinding, overwhelming, magnificent — too much by design, and proud of it.",
    ),
}


def seed_style_vocabulary() -> dict[str, Style]:
    """Seed the ~16-row ``Style`` aesthetic vocabulary across the four audacity
    tiers (#2029): UNDERSTATED/EXPRESSIVE/BOLD/OUTRAGEOUS, four names each.

    Idempotent + authoritative on ``audacity``/``description`` (update_or_create),
    mirroring ``seed_scandal_archetypes`` — tuning/wording tweaks land on reseed
    without row churn.

    Returns:
        Mapping of Style name -> row.
    """
    from world.items.models import Style  # noqa: PLC0415

    styles: dict[str, Style] = {}
    for name, (audacity, description) in _STYLE_VOCABULARY.items():
        style, _ = Style.objects.update_or_create(
            name=name,
            defaults={"audacity": audacity, "description": description},
        )
        styles[name] = style
    return styles


# ---------------------------------------------------------------------------
# Cosmetic items (#1126)
# ---------------------------------------------------------------------------


def seed_cosmetic_items() -> None:
    """Seed starter cosmetic item templates with appearance effects (#1126).

    Creates hair dye ItemTemplates (consumable, 1 charge) with
    ItemTemplateAppearanceEffect rows for hair_color, plus a reusable makeup
    kit. All get_or_create (idempotent).

    Requires FormTrait rows for hair_color etc. to exist (from the forms dev seed).
    """
    from world.forms.models import FormTrait, FormTraitOption  # noqa: PLC0415
    from world.items.models import ItemTemplate, ItemTemplateAppearanceEffect  # noqa: PLC0415

    hair_trait = FormTrait.objects.filter(name="hair_color").first()
    if hair_trait is None:
        return  # forms dev seed hasn't run

    dye_colors = {
        "black": FormTraitOption.objects.filter(trait=hair_trait, name="black").first(),
        "blonde": FormTraitOption.objects.filter(trait=hair_trait, name="blonde").first(),
        "red": FormTraitOption.objects.filter(trait=hair_trait, name="red").first(),
        "auburn": FormTraitOption.objects.filter(trait=hair_trait, name="auburn").first(),
    }
    for color_name, option in dye_colors.items():
        if option is None:
            continue
        template, _ = ItemTemplate.objects.get_or_create(
            name=f"Hair Dye: {color_name.title()}",
            defaults={
                "is_consumable": True,
                "max_charges": 1,
                "is_active": True,
            },
        )
        ItemTemplateAppearanceEffect.objects.get_or_create(
            item_template=template,
            trait=hair_trait,
            defaults={"target_option": option},
        )


# ---------------------------------------------------------------------------
# Consumable food & drink catalog (#2852)
# ---------------------------------------------------------------------------

# (template name, effect kwargs) — PLACEHOLDER magnitudes, author pass on #2852.
_CONSUMABLE_ROWS = (
    (
        "Crusty Bread",
        {"effect_type": "restore_fatigue", "fatigue_amount": 2, "fatigue_category": "physical"},
    ),
    (
        "Hearty Stew",
        {"effect_type": "restore_fatigue", "fatigue_amount": 4, "fatigue_category": "physical"},
    ),
    ("Honeyed Wine", {"effect_type": "intoxicate", "intoxication_potency": 1}),
    ("Strong Ale", {"effect_type": "intoxicate", "intoxication_potency": 2}),
    ("Dwarven Firebrandy", {"effect_type": "intoxicate", "intoxication_potency": 3}),
    ("Cardian Ambrosia", {"effect_type": "restore_anima", "anima_amount": 2}),
    # #2862 — the first drugs; condition names resolve to the Dusted/Hazed
    # ladders (INTOXICATE's intoxicant override).
    (
        "Dream Dust",
        {"effect_type": "intoxicate", "intoxication_potency": 3, "condition": "Dusted"},
    ),
    ("Haze", {"effect_type": "intoxicate", "intoxication_potency": 1, "condition": "Hazed"}),
)


def seed_consumable_catalog() -> None:
    """Seed sample food/drink/ambrosia consumables (#2852).

    Each is a plain consumable ItemTemplate with a deterministic on-use pool
    (no check type — the effect always lands) carrying one Success-tier
    consequence effect: RESTORE_FATIGUE for food, INTOXICATE for drink (the
    whole drunk loop lives behind that one effect), RESTORE_ANIMA for the
    rare magical exception. All rows PLACEHOLDER content for the author pass;
    routed through get_or_create so authored content wins on reload.
    """
    from actions.models import ConsequencePool, ConsequencePoolEntry  # noqa: PLC0415
    from world.checks.models import Consequence, ConsequenceEffect  # noqa: PLC0415
    from world.conditions.intoxication_content import (  # noqa: PLC0415
        ensure_intoxication_content,
    )
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.items.models import ItemTemplate  # noqa: PLC0415
    from world.traits.models import CheckOutcome  # noqa: PLC0415

    ensure_intoxication_content()  # Dusted/Hazed ladders must exist for the drug rows
    outcome, _ = CheckOutcome.objects.get_or_create(name="Success")
    for name, effect_kwargs in _CONSUMABLE_ROWS:
        pool, _created = ConsequencePool.objects.get_or_create(
            name=f"Consume: {name}",
            defaults={"description": f"On-use effects of {name} (#2852)."},
        )
        consequence, _created = Consequence.objects.get_or_create(
            outcome_tier=outcome,
            label=f"{name} consumed",
            defaults={"weight": 1, "character_loss": False},
        )
        ConsequencePoolEntry.objects.get_or_create(pool=pool, consequence=consequence)
        kwargs = dict(effect_kwargs)
        effect_type = kwargs.pop("effect_type")
        condition_name = kwargs.pop("condition", None)
        if condition_name is not None:
            condition = ConditionTemplate.objects.filter(name=condition_name).first()
            if condition is None:
                continue
            kwargs["condition_template"] = condition
        ConsequenceEffect.objects.get_or_create(
            consequence=consequence,
            effect_type=effect_type,
            defaults=kwargs,
        )
        template, created = ItemTemplate.objects.get_or_create(
            name=name,
            defaults={
                "description": f"PLACEHOLDER: {name.lower()} — #2852 consumables catalog.",
                "is_consumable": True,
                "max_charges": 1,
                "is_active": True,
                "on_use_pool": pool,
            },
        )
        # The `if created:` trap (#2724-flavor, see config_prerequisites._crafting_rows):
        # a lore-authored row (name + description only) arrives with no on_use_pool —
        # reattach the mechanics without touching the authored description.
        if not created and template.on_use_pool_id is None:
            template.on_use_pool = pool
            template.is_consumable = True
            template.max_charges = 1
            template.is_active = True
            template.save(
                update_fields=["on_use_pool", "is_consumable", "max_charges", "is_active"]
            )


# ---------------------------------------------------------------------------
# Mounted-combat weapon (#1843)
# ---------------------------------------------------------------------------


def seed_lance_item() -> None:
    """Seed the starter Lance ItemTemplate (#1843).

    Kept out of ``_build_template_specs``/``seed_item_template_starter_catalog``
    (that shared tuple shape has no ``base_weapon_damage`` slot — every row it
    creates gets the field's ``0`` default) so the lance can carry a real
    weapon-damage value without changing the shape for the other ten
    templates. Mirrors ``seed_cosmetic_items``'s standalone get_or_create shape.
    """
    from world.items.constants import BodyRegion, EquipmentLayer, GearArchetype  # noqa: PLC0415
    from world.items.models import ItemTemplate, TemplateSlot  # noqa: PLC0415

    template, _ = ItemTemplate.objects.get_or_create(
        name="Lance",
        defaults={
            "gear_archetype": GearArchetype.LANCE,
            "base_weapon_damage": 6,
            "facet_capacity": 2,
        },
    )
    for region in (BodyRegion.RIGHT_HAND, BodyRegion.LEFT_HAND):
        TemplateSlot.objects.get_or_create(
            template=template,
            body_region=region,
            equipment_layer=EquipmentLayer.BASE,
        )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def seed_items_dev() -> ItemsDevSeedResult:
    """Seed the entire items cluster in one idempotent call.

    Composes:
    1. ``seed_item_template_starter_catalog()`` — one reference template per
       major gear_archetype with TemplateSlot rows.
    2. ``seed_style_vocabulary()`` — the seeded aesthetic Style vocabulary
       spread across the four audacity tiers (#2029).

    All writes are idempotent (get_or_create/update_or_create throughout).
    Re-running on a populated database is a no-op; staff edits to existing
    template rows are preserved (style vocabulary vectors are authoritative
    on reseed, matching seed_scandal_archetypes).

    Returns:
        ItemsDevSeedResult composing all sub-results.
    """
    template_catalog = seed_item_template_starter_catalog()
    styles = seed_style_vocabulary()
    seed_cosmetic_items()
    seed_lance_item()
    seed_consumable_catalog()
    return ItemsDevSeedResult(
        template_catalog=template_catalog,
        styles=styles,
    )
