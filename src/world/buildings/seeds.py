"""Idempotent seed helpers for the buildings system.

Per repo discipline (#683): seeds live in code, called via
``get_or_create``. NOT a committed fixture.

Plan 3 seeds:
- The ``BuildingPermit`` ItemTemplate row (one row; the issue_permit
  effect handler instantiates copies for each issued permit)
- The ``House`` BuildingKind row
"""

from __future__ import annotations

from world.buildings.models import BuildingKind, PropertyGrantProfile
from world.buildings.services import BUILDING_PERMIT_TEMPLATE_NAME

HOUSE_KIND_NAME = "House"


def ensure_building_permit_template():
    """Get-or-create the BuildingPermit ItemTemplate row.

    The permit is a consumable item (max_charges=1). Each issued permit
    is an ItemInstance of this template, decorated by a
    BuildingPermitDetails row carrying the IC parameters.
    """
    from world.items.models import ItemTemplate  # noqa: PLC0415

    template, _ = ItemTemplate.objects.get_or_create(
        name=BUILDING_PERMIT_TEMPLATE_NAME,
        defaults={
            "description": (
                "An authorization to construct a building of a specific "
                "kind in a specific ward. Activate the permit at an outdoor "
                "site within an approved ward to open the construction flow."
            ),
            "is_consumable": True,
            "max_charges": 1,
            "value": 0,
        },
    )
    return template


def ensure_house_kind() -> BuildingKind:
    """Get-or-create the House BuildingKind row (Plan 3's MVP kind)."""
    kind, _ = BuildingKind.objects.get_or_create(
        name=HOUSE_KIND_NAME,
        defaults={
            "description": (
                "A residential dwelling. Plan 3's MVP BuildingKind; other "
                "kinds (manors, taverns, ships, ritual sites, etc.) land "
                "via content authoring."
            ),
            "is_residential": True,
        },
    )
    return kind


# Urban core BuildingKind catalog rows. Each is a staff-authored catalog
# entry with non-exclusive descriptive flags (see BuildingKind model docstring).
# Authored here (not as a fixture) per repo discipline #683.
URBAN_BUILDING_KINDS: tuple[tuple[str, dict[str, bool]], ...] = (
    ("Cottage", {"is_residential": True}),
    ("Tavern", {"is_residential": True, "is_commercial": True}),
    ("Shop", {"is_commercial": True}),
    ("Workshop", {"is_commercial": True}),
    ("Guild Hall", {"is_commercial": True}),
    ("Warehouse", {"is_commercial": True}),
)

URBAN_BUILDING_KIND_DESCRIPTIONS: dict[str, str] = {
    "Cottage": "A small residential dwelling; the rural baseline.",
    "Tavern": "A commercial establishment offering food, drink, and lodging.",
    "Shop": "A commercial storefront for trade and craft.",
    "Workshop": "A production space for manufacturing and fabrication.",
    "Guild Hall": "A headquarters for a guild or organization's operations.",
    "Warehouse": "A commercial storage building for goods and materials.",
}


def ensure_urban_building_kinds() -> None:
    """Get-or-create the urban core BuildingKind rows (#694).

    Six kinds that expand the Builders Guild Clerk's permit menu beyond
    House: Cottage, Tavern, Shop, Workshop, Guild Hall, Warehouse. Each
    carries only the descriptive flags appropriate to its kind — all
    other flags default to False on the model.

    Idempotent — safe to call from test setUp, app startup, or staff
    tooling.
    """
    for name, flags in URBAN_BUILDING_KINDS:
        BuildingKind.objects.get_or_create(
            name=name,
            defaults={
                "description": URBAN_BUILDING_KIND_DESCRIPTIONS[name],
                **flags,
            },
        )


# PLACEHOLDER magnitudes (#670) — ratified super-linear curve (one big build ≈ 2× two
# half-size builds); absolute values await the economy/tuning pass. Admin-editable rows.
BUILDING_SIZE_TIERS: tuple[tuple[int, str, int], ...] = (
    (1, "Hut", 50),
    (2, "Cottage", 125),
    (3, "House", 250),
    (4, "Manor", 600),
    (5, "Estate", 1250),
    (6, "Palace", 2500),
    (7, "Citadel", 5000),
)


def ensure_building_size_tiers() -> None:
    """Get-or-create the building-size budget ladder (#670)."""
    from world.buildings.models import BuildingSizeTier  # noqa: PLC0415

    for tier, name, space_budget in BUILDING_SIZE_TIERS:
        BuildingSizeTier.objects.get_or_create(
            tier=tier, defaults={"name": name, "space_budget": space_budget}
        )


def ensure_default_kind_on_permit_offers() -> None:
    """Set House as default BuildingKind on every PERMIT offer missing one.

    Plan 2's npc_services seed creates PermitOfferDetails rows without a
    building_kind set. Without it, ``issue_permit`` raises
    ``PermitIssuanceError`` — so any role with PERMIT offers (Builders
    Guild Clerk today, future Cult Leader / Sailors' Guild / etc.) needs
    a kind wired before its handlers can run. Patching ALL PERMIT offers
    (not just the clerk's) means future roles inherit a sensible default
    when content authors forget to set one.

    Idempotent — only patches rows where ``building_kind_id IS NULL``.
    """
    from world.npc_services.constants import OfferKind  # noqa: PLC0415
    from world.npc_services.models import NPCServiceOffer  # noqa: PLC0415

    house = ensure_house_kind()
    unwired = NPCServiceOffer.objects.filter(
        kind=OfferKind.PERMIT,
        permit_offer_details__building_kind__isnull=True,
    ).select_related("permit_offer_details")
    for offer in unwired:
        details = offer.permit_offer_details
        details.building_kind = house
        details.save(update_fields=["building_kind"])


# Back-compat alias for callers using the old, clerk-specific name.
ensure_builders_guild_clerk_permits_for_house = ensure_default_kind_on_permit_offers


def ensure_plan_3_seeds() -> None:
    """Convenience: seed everything Plan 3 needs.

    Safe to call multiple times (each component is idempotent).
    """
    ensure_building_permit_template()
    ensure_house_kind()
    ensure_urban_building_kinds()
    ensure_default_kind_on_permit_offers()
    ensure_building_size_tiers()
    # Room-size ladder (#670) lives in evennia_extensions but construction depends
    # on it for the entry room's default size — seed it alongside.
    from evennia_extensions.seeds import ensure_room_size_tiers  # noqa: PLC0415

    ensure_room_size_tiers()


def ensure_architectural_styles() -> None:
    """Seed the style catalog's two tiers (#1469). PLACEHOLDER content throughout.

    Living-realm styles are default-available; throwback styles are
    discovery-gated — each gets a CodexSubject + entry + a CODEX-target Clue
    so the existing clue→RESEARCH pipeline unlocks them end-to-end. Real
    names/prose are authored privately (lore repo) and re-seeded by content
    passes; these rows exist so the mechanism is playable.
    """
    from world.buildings.models import ArchitecturalStyle  # noqa: PLC0415
    from world.clues.constants import ClueResolution, ClueTargetKind  # noqa: PLC0415
    from world.clues.models import Clue  # noqa: PLC0415
    from world.codex.models import CodexCategory, CodexEntry, CodexSubject  # noqa: PLC0415

    for name in ("Vernacular Timberframe", "Harborstone Classical"):
        ArchitecturalStyle.objects.update_or_create(
            name=name,
            defaults={"is_default": True, "prestige_bonus": 0, "cost_multiplier": 1},
        )

    category, _ = CodexCategory.objects.get_or_create(
        name="Architecture",
        defaults={"description": "PLACEHOLDER — the built world's styles and lost arts."},
    )
    throwbacks = (
        ("Antique Imperial", 50, "1.500"),
        ("Drowned Dynasty", 80, "2.000"),
    )
    for style_name, prestige_bonus, cost_multiplier in throwbacks:
        subject, _ = CodexSubject.objects.get_or_create(
            category=category,
            name=style_name,
            defaults={"description": "PLACEHOLDER — a dead civilization's architecture."},
        )
        entry, _ = CodexEntry.objects.get_or_create(
            subject=subject,
            name=f"Building in the {style_name} manner",
            defaults={
                "summary": "PLACEHOLDER — how to raise this style true.",
                "lore_content": (
                    "PLACEHOLDER — the recovered method of a vanished tradition; "
                    "knowing it lets a builder raise the style correctly."
                ),
            },
        )
        ArchitecturalStyle.objects.update_or_create(
            name=style_name,
            defaults={
                "is_default": False,
                "prestige_bonus": prestige_bonus,
                "cost_multiplier": cost_multiplier,
                "codex_subject": subject,
            },
        )
        Clue.objects.get_or_create(
            name=f"Fragments of the {style_name}",
            defaults={
                "description": (
                    "PLACEHOLDER — salvaged plans and weathered facades hinting at a "
                    "buildable whole."
                ),
                "target_kind": ClueTargetKind.CODEX,
                "target_codex_entry": entry,
                "resolution_mode": ClueResolution.RESEARCH,
            },
        )


def ensure_decoration_kinds() -> None:
    """Seed comfort-fixture kinds (#1514/#1469 follow-through). PLACEHOLDER content.

    The mitigation fixtures the build-to-win loop needs playable: each kind's
    affinities are negative modifiers that eat one discomfort axis (the 0-floor
    means they can never harm). Magnitudes are PLACEHOLDER for the tuning pass.
    """
    from world.buildings.models import DecorationAffinity, DecorationKind  # noqa: PLC0415
    from world.locations.constants import StatKey  # noqa: PLC0415

    kinds = (
        ("Great Hearth", 1, ((StatKey.COLD, -4),)),
        ("Oiled Awning", 0, ((StatKey.WET, -3),)),
        ("Shade Colonnade", 0, ((StatKey.HEAT, -3),)),
    )
    for name, amenity, affinities in kinds:
        kind, _ = DecorationKind.objects.update_or_create(
            name=name,
            defaults={
                "description": "PLACEHOLDER — a comfort fixture awaiting its authored prose.",
                "amenity": amenity,
            },
        )
        for stat_key, value in affinities:
            DecorationAffinity.objects.update_or_create(
                kind=kind, stat_key=stat_key, defaults={"value": value}
            )


PREPARATION_METHOD_NAME = "Direct the Household"


def ensure_preparation_contribution_method() -> None:
    """Seed the AP-check contribution method for Grand Preparation (#1930).

    ``Household Command`` (presence + Leadership + Stewardship, the #930
    governance seed) is the check — rallying your household to scrub,
    polish, and hang the garlands. Depends on the governance content;
    calls its idempotent seed to guarantee the composed CheckType exists.
    AP cost / progress magnitudes are PLACEHOLDER (tuning ledger §6).
    """
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.projects.constants import ProjectKind  # noqa: PLC0415
    from world.projects.models import ContributionMethod  # noqa: PLC0415
    from world.seeds.governance_checks import seed_governance_check_content  # noqa: PLC0415

    check_type = CheckType.objects.filter(name="Household Command").first()
    if check_type is None:
        seed_governance_check_content()
        check_type = CheckType.objects.get(name="Household Command")

    ContributionMethod.objects.update_or_create(
        kind=ProjectKind.BUILDING_PREPARATION,
        name=PREPARATION_METHOD_NAME,
        defaults={
            "description": (
                "PLACEHOLDER — rally the household to scrub, polish, and prepare; "
                "a successful command speeds the preparation along."
            ),
            "check_type": check_type,
            "ap_cost": 5,
            "progress_on_success": 10,
        },
    )


PLACEHOLDER_PROPERTY_GRANT_KIND_NAME = "Unclaimed Property (placeholder)"
PLACEHOLDER_PROPERTY_GRANT_PROFILE_NAME = "Generic Property Grant (placeholder)"


def ensure_placeholder_property_grant_profile() -> PropertyGrantProfile:
    """Get-or-create a generic dev/test PropertyGrantProfile.

    Not content — a schema-exercising placeholder so grant_property_house is
    testable end-to-end before any real fixture content wires a Beginnings
    row at a PropertyGrantProfile.
    """
    from world.buildings.models import BuildingKind  # noqa: PLC0415

    kind, _ = BuildingKind.objects.get_or_create(
        name=PLACEHOLDER_PROPERTY_GRANT_KIND_NAME,
        defaults={
            "description": "Placeholder catalog kind for dev/test property grants.",
            "is_residential": True,
        },
    )
    profile, _ = PropertyGrantProfile.objects.get_or_create(
        name=PLACEHOLDER_PROPERTY_GRANT_PROFILE_NAME,
        defaults={"building_kind": kind},
    )
    return profile
