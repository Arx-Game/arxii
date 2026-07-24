"""Styling & makeover seed content (#2632).

Item flavor is ApostateCD's (2026-07-22 flavor sweep) — deliberately generic
for dye bottles ("the prose is really in people deciding the specific types
derived from that"), verbatim prose for Ariwn Lenses and Prism's Dye. NPC
role/offer flavor remains PLACEHOLDER pending the next sweep batch.

Three pieces, all idempotent:

- Cosmetic item templates: one generic "<Color> Dye" per hair color, ONE
  reusable Styling Kit and the Ariwn Lenses (both choose-at-use — the wearer
  names the option, the lens "takes a drop of dye"), and Prism's Dye (the
  magical prismatic shimmer).
- The "Silver Shears Stylist" NPC role with menu-driven STYLING offers
  (one per (trait, option); prismatic/multihued excluded — magic dye and the
  pending dye-composition mechanics respectively).
- The "Great Archive Profile Scribe" role with the PROFILE_RECORDING offer.

Depends on the character_creation appearance-trait seeds (hair_color,
hair_style, eye_color rows); missing traits are skipped, not created here.
"""

from __future__ import annotations

STYLIST_ROLE_NAME = "Silver Shears Stylist"
PROFILE_SCRIBE_ROLE_NAME = "Great Archive Profile Scribe"

_STYLING_PRICE_COPPERS = 100  # PLACEHOLDER magnitudes
_PROFILE_SITTING_PRICE_COPPERS = 500  # PLACEHOLDER magnitudes

#: Basic chromatic + natural dye colors (ApostateCD 2026-07-22): one generic
#: "<Color> Dye" bottle per hair-color option. Deliberately plain — the prose
#: lives in the specific looks players derive from them, not in the bottles.
_DYE_COLOR_OPTIONS: tuple[str, ...] = (
    "black",
    "brown",
    "blonde",
    "red",
    "auburn",
    "white",
    "gray",
    "blue",
    "green",
    "yellow",
    "violet",
    "orange",
)

#: Fixed-option non-dye cosmetics: (name, description, trait, option, targetable,
#: consumable). Prose is ApostateCD's — verbatim, not PLACEHOLDER.
_PRISMS_DYE_DESC = (
    "Named after a fabled Seraph of Choice, this dye is thought to be blended "
    "with magical light, and causes hair to shimmer in a prismatic array once "
    "applied."
)

#: Choose-at-use cosmetics: (name, description, trait, targetable, consumable).
#: A null target_option means the wearer names the option at use time.
_ARIWN_LENSES_DESC = (
    "Thought to have an extremely minor enchantment, the lenses can take a "
    "single drop of dye and then have the translucent strips placed over "
    "one's eye, mirror an entire other eye color. Popular among the nobility "
    "of Ariwn when traveling incognito, as the all too common crimson eyes "
    "would frequently give them away."
)


def seed_styling_content() -> None:
    """Seed cosmetic item templates + stylist/scribe roles and offers."""
    _seed_cosmetic_templates()
    _seed_exotic_style()
    _seed_stylist_role()
    _seed_profile_scribe_role()


def _seed_exotic_style() -> None:
    """One PLACEHOLDER exotic (requires_teaching) hair style (#2632).

    Exercises the learned/taught loop end to end on a fresh DB: the stylist's
    menu offers it (having it done teaches it), after which the player can
    maintain it with their own Styling Kit. Name PLACEHOLDER pending
    ApostateCD's style-list batch.
    """
    from world.forms.models import FormTrait, FormTraitOption  # noqa: PLC0415

    trait = FormTrait.objects.filter(name="hair_style", is_cosmetic=True).first()
    if trait is None:
        return
    FormTraitOption.objects.get_or_create(
        trait=trait,
        name="court_coils",
        defaults={
            "display_name": "Court Coils",
            "sort_order": 90,
            "requires_teaching": True,
        },
    )


def _ensure_cosmetic_template(  # noqa: PLR0913
    *,
    name: str,
    description: str,
    trait_name: str,
    option_name: str | None,
    targetable: bool,
    consumable: bool,
) -> None:
    """Idempotently seed one cosmetic template + its appearance effect.

    ``option_name=None`` seeds a choose-at-use effect (null target_option).
    Skips gracefully when the trait (or named option) isn't seeded/cosmetic.
    """
    from actions.constants import TargetKind  # noqa: PLC0415
    from world.forms.models import FormTrait, FormTraitOption  # noqa: PLC0415
    from world.items.models import ItemTemplate, ItemTemplateAppearanceEffect  # noqa: PLC0415

    trait = FormTrait.objects.filter(name=trait_name, is_cosmetic=True).first()
    if trait is None:
        return
    option = None
    if option_name is not None:
        option = FormTraitOption.objects.filter(trait=trait, name=option_name).first()
        if option is None:
            return
    template, _ = ItemTemplate.objects.get_or_create(
        name=name,
        defaults={
            "description": description,
            "is_consumable": consumable,
            "max_charges": 1 if consumable else 0,
            "on_use_target_kind": TargetKind.CHARACTER if targetable else None,
        },
    )
    ItemTemplateAppearanceEffect.objects.get_or_create(
        item_template=template,
        trait=trait,
        defaults={"target_option": option},
    )


def _seed_cosmetic_templates() -> None:
    from world.forms.models import FormTraitOption  # noqa: PLC0415

    # Generic dye bottles — one per color, plain by design.
    for option_name in _DYE_COLOR_OPTIONS:
        option = FormTraitOption.objects.filter(trait__name="hair_color", name=option_name).first()
        display = option.display_name if option else option_name.capitalize()
        _ensure_cosmetic_template(
            name=f"{display} Dye",
            description=f"A bottle of {display.lower()} dye.",
            trait_name="hair_color",
            option_name=option_name,
            targetable=True,
            consumable=True,
        )

    # One reusable Styling Kit — the wearer picks the style at use.
    _ensure_cosmetic_template(
        name="Styling Kit",
        description="A kit used for hair styling.",
        trait_name="hair_style",
        option_name=None,
        targetable=True,
        consumable=False,
    )

    # Ariwn Lenses — choose-at-use eye color (the "drop of dye" mechanized).
    _ensure_cosmetic_template(
        name="Ariwn Lenses",
        description=_ARIWN_LENSES_DESC,
        trait_name="eye_color",
        option_name=None,
        targetable=False,
        consumable=False,
    )

    # Prism's Dye — the magical shimmer, distinct from mundane multihued combos.
    _ensure_cosmetic_template(
        name="Prism's Dye",
        description=_PRISMS_DYE_DESC,
        trait_name="hair_color",
        option_name="prismatic",
        targetable=True,
        consumable=True,
    )


def _seed_stylist_role() -> None:
    from world.forms.models import FormTrait  # noqa: PLC0415
    from world.npc_services.constants import OfferKind  # noqa: PLC0415
    from world.npc_services.models import (  # noqa: PLC0415
        NPCRole,
        NPCServiceOffer,
        StylingOfferDetails,
    )

    role, _ = NPCRole.objects.get_or_create(
        name=STYLIST_ROLE_NAME,
        defaults={
            "description": "PLACEHOLDER — a fashionable stylist for hire.",
            "default_description_template": (
                "PLACEHOLDER — scissors flash; the stylist appraises your look."
            ),
            "default_rapport_starting_value": 0,
        },
    )

    # Prismatic is Prism's Dye's magic (not a salon service) and multihued
    # awaits the dye-composition mechanics — neither is a stylist menu row.
    excluded_options = {"prismatic", "multihued"}
    for trait_name in ("hair_color", "hair_style"):
        trait = FormTrait.objects.filter(name=trait_name, is_cosmetic=True).first()
        if trait is None:
            continue
        for option in trait.options.exclude(name__in=excluded_options):
            label = f"{trait.display_name}: {option.display_name}"
            offer, created = NPCServiceOffer.objects.get_or_create(
                role=role,
                label=label,
                defaults={
                    "kind": OfferKind.STYLING,
                    "is_final": True,
                },
            )
            if created:
                StylingOfferDetails.objects.create(
                    offer=offer,
                    trait=trait,
                    target_option=option,
                    price_coppers=_STYLING_PRICE_COPPERS,
                )


def _seed_profile_scribe_role() -> None:
    from world.npc_services.constants import OfferKind  # noqa: PLC0415
    from world.npc_services.models import (  # noqa: PLC0415
        NPCRole,
        NPCServiceOffer,
        ProfileRecordingOfferDetails,
    )

    role, _ = NPCRole.objects.get_or_create(
        name=PROFILE_SCRIBE_ROLE_NAME,
        defaults={
            "description": (
                "PLACEHOLDER — an Archive scholar who records profiles of "
                "notable persons for posterity."
            ),
            "default_description_template": (
                "PLACEHOLDER — ink-stained fingers pause over a fresh page."
            ),
            "default_rapport_starting_value": 0,
        },
    )
    offer, created = NPCServiceOffer.objects.get_or_create(
        role=role,
        label="Commission a recorded profile",
        defaults={
            "kind": OfferKind.PROFILE_RECORDING,
            "is_final": True,
        },
    )
    if created:
        ProfileRecordingOfferDetails.objects.create(
            offer=offer, price_coppers=_PROFILE_SITTING_PRICE_COPPERS
        )
