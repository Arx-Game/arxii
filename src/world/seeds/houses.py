"""Houses demo seed (#1884) — the kinship demo house made a landed peer.

PLACEHOLDER content. Idempotent get-or-create keyed on names. Rides the
kinship cluster's House Veyrane: gives it an Organization, a nobiliary
particle, realm recognition rules, a succession law, a liege (the seed
crown), a ducal title seated on a domain, and one working holding feeding
the org books — enough to walk the house page, sheet/house, succession
derivation, and the feed on a dev DB.

``SuccessionLaw``, ``HoldingKind``, ``HouseTemplate`` and ``HouseFeature`` are
authored content (#2875 — see ``docs/systems/houses.md``): this module looks
them up via ``authored_or_sample`` rather than inventing them with
``get_or_create``, so a real content universe's rows win and nothing here
lands in the export. The Crown organization and its Society are plain
seeder-owned config (neither is in ``CONTENT_MODELS``), but content-repo
``HouseTemplate``/``SuccessionLaw`` rows can FK them by name, so their
creation moved to ``world.seeds.config_prerequisites._house_charter_anchors``
via ``_ensure_house_charter_anchors`` below, which runs before the content
load. ``seed_houses_demo`` calls the same helper again once "Arx" is
available, the self-healing pattern ADR-0171 describes.
"""

from __future__ import annotations

# Canon nobiliary particles (#3261, ratified 2026-08-17) keyed by Realm.theme:
# (tier_floor, born particle, taken-in particle). Blank floor = default band.
# Arx has NO rows by canon — it has no nobility; bare names are its signature.
CANON_NOBILIARY_PARTICLES: dict[str, tuple[tuple[str, str, str], ...]] = {
    "luxen": (("duchy", "du", "dau"), ("", "D'", "dau")),
    "umbros": (("empire", "mar", "mal"), ("", "arn", "ard")),
    "inferna": (("kingdom", "aza", "azas"), ("", "za", "zas")),
    "ariwn": (("", "ul", "vosk"),),
    "aythirmok": (("", "jor", "jorn"),),
}


def seed_nobiliary_particles() -> None:
    """Upsert the canon particle rows onto every authored realm, by theme.

    ``update_or_create`` (not ``get_or_create``) so canon overwrites any
    placeholder rows already in a dev DB (idmapper rows don't update via
    loaddata — #946).
    """
    from world.realms.models import Realm  # noqa: PLC0415
    from world.roster.constants import NOBLE_KIND_NAME  # noqa: PLC0415
    from world.roster.seeds import ensure_family_kinds  # noqa: PLC0415
    from world.societies.houses.models import NobiliaryParticle  # noqa: PLC0415

    noble_kind = ensure_family_kinds()[NOBLE_KIND_NAME]
    for realm in Realm.objects.filter(theme__in=CANON_NOBILIARY_PARTICLES):
        for tier_floor, born, taken_in in CANON_NOBILIARY_PARTICLES[realm.theme]:
            NobiliaryParticle.objects.update_or_create(
                realm=realm,
                kind=noble_kind,
                tier_floor=tier_floor,
                defaults={"particle": born, "taken_in_particle": taken_in},
            )


CROWN_ORG_NAME = "The Crown of Arx PLACEHOLDER"
SOCIETY_NAME = "PLACEHOLDER Peerage of Arx"
HOUSE_ORG_NAME = "House Veyrane PLACEHOLDER"
DUCAL_TITLE_NAME = "Duchy of Veyrane PLACEHOLDER"
DOMAIN_NAME = "Veyrane Vale PLACEHOLDER"
CLAIMABLE_TITLE_NAME = "Barony of Thornmere PLACEHOLDER"
CLAIMABLE_DOMAIN_NAME = "Thornmere Marches PLACEHOLDER"
TEMPLATE_NAME = "Arx Barony Charter PLACEHOLDER"


def _ensure_house_charter_anchors(realm) -> tuple:
    """Ensure the Crown org + its Society exist under ``realm`` (idempotent).

    Neither model is in ``CONTENT_MODELS`` (#2875) — they are plain
    seeder-owned config — but content-repo ``HouseTemplate``/``SuccessionLaw``
    rows can FK the Crown and its Society by name, so both must exist before
    the content load resolves those fixtures. Called two ways: once from
    ``world.seeds.config_prerequisites._house_charter_anchors`` (before
    ``load_content_first()``, with its own ``realm`` resolution — a no-op
    there on a database with no "Arx" realm authored yet), and again from
    ``seed_houses_demo`` after the content load, once ``realm`` is actually
    available (the self-healing gameplay-call-site pattern ADR-0171
    describes for a code-required row).

    Returns ``(society, org_type, crown)``.
    """
    from world.societies.models import Organization, OrganizationType, Society  # noqa: PLC0415

    society, _ = Society.objects.get_or_create(
        name=SOCIETY_NAME,
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
    crown, _ = Organization.objects.get_or_create(
        name=CROWN_ORG_NAME,
        defaults={
            "description": "PLACEHOLDER: the throne all fealty flows toward.",
            "society": society,
            "org_type": org_type,
        },
    )
    return society, org_type, crown


def seed_houses_demo() -> None:
    """Seed the PLACEHOLDER landed house (idempotent).

    ``realms.Realm`` is content-repo-owned (#2698) — looked up rather than
    invented unless ``SEED_SAMPLE_CONTENT`` is on. When the "Arx" realm isn't
    authored/sampled, this skips everything past ``seed_kinship_demo()`` —
    Society/Organization/Title/SuccessionLaw all hang off ``realm`` via a
    required FK.
    """
    from world.areas.constants import AreaLevel  # noqa: PLC0415
    from world.areas.models import Area  # noqa: PLC0415
    from world.realms.models import Realm  # noqa: PLC0415
    from world.roster.models import Family  # noqa: PLC0415
    from world.seeds.kinship import DUCAL_HOUSE_NAME, seed_kinship_demo  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415
    from world.societies.houses.constants import (  # noqa: PLC0415
        RecognitionRuleKind,
        SuccessionDerivation,
        SuccessionOrdering,
        TitleTier,
    )
    from world.societies.houses.models import (  # noqa: PLC0415
        HoldingKind,
        HouseRecognitionRule,
        SuccessionLaw,
        Title,
    )
    from world.societies.houses.services import (  # noqa: PLC0415
        add_holding,
        create_domain,
        swear_fealty,
    )
    from world.societies.models import Organization  # noqa: PLC0415

    seed_kinship_demo()
    seed_nobiliary_particles()
    family = Family.objects.get(name=DUCAL_HOUSE_NAME)

    realm = authored_or_sample(
        Realm,
        {"description": "The default realm.", "crest_asset": "", "theme": ""},
        name="Arx",
    )
    if realm is None:
        return
    society, org_type, crown = _ensure_house_charter_anchors(realm)
    law = authored_or_sample(
        SuccessionLaw,
        {
            "derivation": SuccessionDerivation.PRIMOGENITURE_WEDLOCK,
            "ordering_rule": SuccessionOrdering.ELDEST,
            "require_wedlock": True,
        },
        name="Veyrane Primogeniture PLACEHOLDER",
    )
    if law is None:
        return
    _seed_house_creator(realm=realm, society=society, crown=crown, law=law)

    house, created = Organization.objects.get_or_create(
        name=HOUSE_ORG_NAME,
        defaults={
            "description": "PLACEHOLDER: the ducal house of the kinship demo tree.",
            "society": society,
            "org_type": org_type,
            "family": family,
            "default_succession_law": law,
        },
    )
    if not created:
        return

    for kind in (
        RecognitionRuleKind.MATRILINEAL_AUTO_WEDLOCK,
        RecognitionRuleKind.MOTHER_OPTION_OUT_OF_WEDLOCK,
    ):
        HouseRecognitionRule.objects.get_or_create(realm=realm, kind=kind)

    swear_fealty(vassal=house, liege=crown)

    area, _ = Area.objects.get_or_create(name=DOMAIN_NAME, defaults={"level": AreaLevel.REGION})
    domain = create_domain(area=area, name=DOMAIN_NAME, owner_org=house)
    farmland = authored_or_sample(
        HoldingKind,
        {
            "description": "PLACEHOLDER: grain terraces and tenant farms.",
            "stream_kind": "domain_tax",
            "base_gross": 1000,
        },
        name="Farmland PLACEHOLDER",
    )
    if farmland is None:
        return
    add_holding(domain=domain, kind=farmland)

    duchess = family.members.filter(name__startswith="Duchess").first()
    Title.objects.get_or_create(
        name=DUCAL_TITLE_NAME,
        defaults={
            "tier": TitleTier.DUCHY,
            "realm": realm,
            "house": house,
            "holder": duchess,
            "seat_domain": domain,
        },
    )


def _seed_house_creator(*, realm, society, crown, law) -> None:
    """Phase D: a set-aside claimable barony + the realm's charter template."""
    from world.areas.constants import AreaLevel  # noqa: PLC0415
    from world.areas.models import Area  # noqa: PLC0415
    from world.roster.constants import NOBLE_KIND_NAME  # noqa: PLC0415
    from world.roster.seeds import ensure_family_kinds  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415
    from world.societies.houses.constants import TitleTier  # noqa: PLC0415
    from world.societies.houses.models import (  # noqa: PLC0415
        Domain,
        HoldingKind,
        HouseAspectDefinition,
        HouseAspectOption,
        HouseFeature,
        HouseTemplate,
        Title,
    )

    noble_kind = ensure_family_kinds()[NOBLE_KIND_NAME]
    farmland = authored_or_sample(
        HoldingKind,
        {
            "description": "PLACEHOLDER: grain terraces and tenant farms.",
            "stream_kind": "domain_tax",
            "base_gross": 1000,
        },
        name="Farmland PLACEHOLDER",
    )
    if farmland is None:
        return
    template = authored_or_sample(
        HouseTemplate,
        {
            "description": "PLACEHOLDER: the standard charter for a landed barony of Arx.",
            "realm": realm,
            "kind": noble_kind,
            "society": society,
            "liege": crown,
            "default_succession_law": law,
        },
        name=TEMPLATE_NAME,
    )
    if template is None:
        return
    template.holdings.add(farmland)

    # #2079 — one exemplar aspect definition + feature proving the loop.
    # #2868: the aspect catalog is now content-repo-owned, so it is looked up
    # and only invented under SEED_SAMPLE_CONTENT. When the content repo
    # authors real catalogs (Inferna's Quiddities), this placeholder is absent
    # and the template simply carries no aspect definitions from the seeder.
    virtue = authored_or_sample(
        HouseAspectDefinition,
        {"prompt": "PLACEHOLDER: which virtue did your house cling to?"},
        name="House Virtue PLACEHOLDER",
    )
    if virtue is not None:
        for order, (option_name, blurb) in enumerate(
            [
                ("Fortitude PLACEHOLDER", "PLACEHOLDER: endurance without breaking."),
                ("Candor PLACEHOLDER", "PLACEHOLDER: truth spoken plainly."),
                ("Charity PLACEHOLDER", "PLACEHOLDER: the open hand."),
            ]
        ):
            authored_or_sample(
                HouseAspectOption,
                {"description": blurb, "display_order": order},
                definition=virtue,
                name=option_name,
            )
        template.aspect_definitions.add(virtue)
    hearth = authored_or_sample(
        HouseFeature,
        {
            "slug": "hearth-right-placeholder",
            "description": "PLACEHOLDER: guests under the house's roof are sacrosanct.",
        },
        name="Hearth Right PLACEHOLDER",
    )
    if hearth is not None:
        template.features.add(hearth)

    seat_area, _ = Area.objects.get_or_create(
        name=CLAIMABLE_DOMAIN_NAME, defaults={"level": AreaLevel.REGION}
    )
    seat, _ = Domain.objects.get_or_create(
        area=seat_area,
        defaults={"name": CLAIMABLE_DOMAIN_NAME, "owner_org": crown},
    )
    Title.objects.get_or_create(
        name=CLAIMABLE_TITLE_NAME,
        defaults={
            "tier": TitleTier.BARONY,
            "realm": realm,
            "seat_domain": seat,
            "is_claimable": True,
        },
    )
