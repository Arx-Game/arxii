"""Dev domain-running slice (#930/#1464 follow-through) — a walkable books loop.

Makes this week's systems demo-able on a freshly seeded dev DB: a PLACEHOLDER
house with income streams, a House Steward role carrying the COLLECTION /
IMPROVEMENT offers (so the books page's Collect button opens a dialog with
something in it), and two PLACEHOLDER scandal archetypes so the #1464 fork has
vocabulary to judge. Every player-visible string is PLACEHOLDER — the real
vocabulary (crime kinds beyond the starter pair, laws, the deed-type↔principle
mapping, offer flavor) is Apostate's authoring pass. Laws (`AreaLaw`) are world
data attached to authored areas and are deliberately NOT seeded here.

Idempotent get_or_creates throughout; mirrors ``npc_services.seeds``.
"""

from __future__ import annotations

from datetime import timedelta

DEV_HOUSE_NAME = "PLACEHOLDER House Amberfall"
STEWARD_ROLE_NAME = "House Steward"


def ensure_dev_domain() -> None:
    """Seed the walkable domain loop: house, streams, steward, offers, archetypes."""
    _ensure_scandal_archetypes()
    organization = _ensure_house()
    _ensure_income_streams(organization)
    _ensure_steward_offers(organization)


def _ensure_house():
    from world.realms.models import Realm  # noqa: PLC0415
    from world.societies.models import Organization, OrganizationType, Society  # noqa: PLC0415

    realm, _ = Realm.objects.get_or_create(
        name="Arx",
        defaults={"description": "The default realm.", "crest_asset": "", "theme": ""},
    )
    society, _ = Society.objects.get_or_create(
        name="PLACEHOLDER Peerage of Arx",
        defaults={"description": "PLACEHOLDER: the landed nobility.", "realm": realm},
    )
    org_type, _ = OrganizationType.objects.get_or_create(
        name="noble_family",
        defaults={
            "rank_1_title": "Head of House",
            "rank_2_title": "Voice",
            "rank_3_title": "Noble Family",
            "rank_4_title": "Trusted House Servants",
            "rank_5_title": "Servants",
        },
    )
    organization, _ = Organization.objects.get_or_create(
        name=DEV_HOUSE_NAME,
        defaults={
            "description": "PLACEHOLDER: a modest house with modest ledgers.",
            "society": society,
            "org_type": org_type,
        },
    )
    return organization


def _ensure_income_streams(organization) -> None:
    from world.currency.models import OrgIncomeStream  # noqa: PLC0415

    for name, kind, gross in (
        ("PLACEHOLDER Amberfall land taxes", "domain_tax", 1000),
        ("PLACEHOLDER river toll kick-up", "crime_kickup", 400),
    ):
        OrgIncomeStream.objects.get_or_create(
            organization=organization,
            name=name,
            defaults={"kind": kind, "gross_amount": gross},
        )


def _ensure_steward_offers(organization) -> None:
    from world.npc_services.constants import DrawMode, OfferKind  # noqa: PLC0415
    from world.npc_services.models import NPCRole, NPCServiceOffer  # noqa: PLC0415

    role, _ = NPCRole.objects.get_or_create(
        name=STEWARD_ROLE_NAME,
        defaults={
            "description": "PLACEHOLDER: keeps the house's books and directs its people.",
            "default_description_template": (
                "PLACEHOLDER: The steward looks up from a ledger thick with tallies."
            ),
            "default_rapport_starting_value": 0,
            "faction_affiliation": organization,
        },
    )
    for label, kind in (
        ("Dispatch a collection", OfferKind.COLLECTION),
        ("Invest in the domain", OfferKind.IMPROVEMENT),
    ):
        NPCServiceOffer.objects.get_or_create(
            role=role,
            label=label,
            defaults={
                "kind": kind,
                "draw_mode": DrawMode.MENU,
                "eligibility_rule": {},
                "rapport_requirement": 0,
                "is_final": True,
                "ap_cost": 2,  # PLACEHOLDER
                "cooldown": timedelta(days=1),  # PLACEHOLDER
            },
        )


def _ensure_scandal_archetypes() -> None:
    """Two PLACEHOLDER rows so the #1464 judgment has vocabulary to read.

    Deltas are PLACEHOLDER signs, not tuning: one reads badly to honor-bound
    societies (oath-breaking shape), one to hierarchical ones (insolence
    shape). Apostate's deed-type↔principle mapping pass replaces/extends these.
    """
    from world.societies.models import PhilosophicalArchetype  # noqa: PLC0415

    for name, deltas in (
        ("PLACEHOLDER Oathbreaking", {"method_delta": -2, "allegiance_delta": -1}),
        ("PLACEHOLDER Insolence", {"power_delta": -2, "status_delta": -1}),
    ):
        PhilosophicalArchetype.objects.get_or_create(
            name=name,
            defaults={
                "description": "PLACEHOLDER: awaiting the authored archetype pass.",
                **deltas,
            },
        )
