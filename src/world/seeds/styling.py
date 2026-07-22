"""Styling & makeover seed content (#2632). All flavor PLACEHOLDER.

Three pieces, all idempotent:

- Cosmetic item templates (a targetable dye, a styling kit, the enchanted
  eye lenses that ARE the eye-color gate) with their appearance effects.
- The "Silver Shears Stylist" NPC role with menu-driven STYLING offers
  (one per (trait, option) — the interaction machinery is menu-driven).
- The "Great Archive Profile Scribe" role with the PROFILE_RECORDING offer.

Depends on the character_creation appearance-trait seeds (hair_color,
hair_style, eye_color rows); missing traits are skipped, not created here.
"""

from __future__ import annotations

STYLIST_ROLE_NAME = "Silver Shears Stylist"
PROFILE_SCRIBE_ROLE_NAME = "Great Archive Profile Scribe"

_STYLING_PRICE_COPPERS = 100  # PLACEHOLDER magnitudes
_PROFILE_SITTING_PRICE_COPPERS = 500  # PLACEHOLDER magnitudes

#: (template name, trait name, option name, targetable) — targetable templates
#: set on_use_target_kind=CHARACTER so PC stylists can apply them to others.
_COSMETIC_TEMPLATES: tuple[tuple[str, str, str, bool], ...] = (
    ("Vermilion Hair Dye PLACEHOLDER", "hair_color", "red", True),
    ("Braiding Kit PLACEHOLDER", "hair_style", "braided", True),
    ("Enchanted Azure Lenses PLACEHOLDER", "eye_color", "blue", False),
)


def seed_styling_content() -> None:
    """Seed cosmetic item templates + stylist/scribe roles and offers."""
    _seed_cosmetic_templates()
    _seed_stylist_role()
    _seed_profile_scribe_role()


def _seed_cosmetic_templates() -> None:
    from actions.constants import TargetKind  # noqa: PLC0415
    from world.forms.models import FormTrait, FormTraitOption  # noqa: PLC0415
    from world.items.models import ItemTemplate, ItemTemplateAppearanceEffect  # noqa: PLC0415

    for template_name, trait_name, option_name, targetable in _COSMETIC_TEMPLATES:
        trait = FormTrait.objects.filter(name=trait_name, is_cosmetic=True).first()
        if trait is None:
            continue  # appearance seeds haven't run (or the trait isn't cosmetic)
        option = FormTraitOption.objects.filter(trait=trait, name=option_name).first()
        if option is None:
            continue
        template, _ = ItemTemplate.objects.get_or_create(
            name=template_name,
            defaults={
                "description": "PLACEHOLDER — cosmetic awaiting authored prose.",
                "is_consumable": True,
                "max_charges": 1,
                "on_use_target_kind": TargetKind.CHARACTER if targetable else None,
            },
        )
        ItemTemplateAppearanceEffect.objects.get_or_create(
            item_template=template,
            trait=trait,
            defaults={"target_option": option},
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

    for trait_name in ("hair_color", "hair_style"):
        trait = FormTrait.objects.filter(name=trait_name, is_cosmetic=True).first()
        if trait is None:
            continue
        for option in trait.options.all():
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
