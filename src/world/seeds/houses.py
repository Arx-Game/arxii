"""Houses demo seed (#1884) — the kinship demo house made a landed peer.

PLACEHOLDER content. Idempotent get-or-create keyed on names. Rides the
kinship cluster's House Veyrane: gives it an Organization, a nobiliary
particle, realm recognition rules, a succession law, a liege (the seed
crown), a ducal title seated on a domain, one working holding feeding the
org books, and a ``published_at`` (via ``almanach.publish_house``) so the
demo house is Almanach-visible out of the box — enough to walk the house
page, sheet/house, succession derivation, and the feed on a dev DB.

``SuccessionLaw``, ``HoldingKind``, ``HouseTemplate``, ``HouseFeature`` and
``LandShape`` are authored content (#2875/#3983, see
``docs/systems/houses.md``): this module looks them up via
``authored_or_sample`` rather than inventing them with ``get_or_create``, so a
real content universe's rows win and nothing here lands in the export. The
Crown organization and its Society are plain seeder-owned config (neither is
in ``CONTENT_MODELS``), but content-repo ``HouseTemplate``/``SuccessionLaw``
rows can FK them by name, so their creation moved to
``world.seeds.config_prerequisites._house_charter_anchors`` via
``_ensure_house_charter_anchors`` below, which runs before the content load.
``seed_houses_demo`` calls the same helper again once "Arx" is available, the
self-healing pattern ADR-0171 describes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.realms.models import Realm
    from world.societies.models import Organization, OrganizationType, Society

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


# Authored land-shape catalog (#3983): what a demesne's ground looks like,
# picked in ``describe_demesne``'s ``land_shape_names`` list. Content-owned
# (``societies.landshape`` is in ``CONTENT_MODELS``), so this seeds it the
# same ``authored_or_sample`` way the charter models above are seeded rather
# than a plain ``get_or_create`` (#2698: a seeder never invents content).
LAND_SHAPES: tuple[tuple[str, str], ...] = (
    ("Coast", "PLACEHOLDER: cliffs and harbor towns facing open water."),
    ("Reefs", "PLACEHOLDER: shoals and barrier reefs working the shallows offshore."),
    ("Hills", "PLACEHOLDER: rolling upland pasture and terraced slopes."),
    ("Volcanic", "PLACEHOLDER: ash-fed soil under an active or dormant cone."),
    ("Marsh", "PLACEHOLDER: wetland fen, difficult to ford."),
    ("Forest", "PLACEHOLDER: dense timberland, close-canopied."),
)


def seed_land_shapes() -> None:
    """Look up (or, under ``SEED_SAMPLE_CONTENT``, invent) the authored
    ``LandShape`` catalog. Independent of any realm — a plain content lookup,
    not gated on "Arx" existing — so it seeds even when the rest of
    ``seed_houses_demo`` returns early for lack of an authored realm.
    """
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415
    from world.societies.houses.models import LandShape  # noqa: PLC0415

    for order, (name, description) in enumerate(LAND_SHAPES):
        authored_or_sample(LandShape, {"description": description, "sort_order": order}, name=name)


CROWN_ORG_NAME = "The Crown of Arx PLACEHOLDER"
SOCIETY_NAME = "PLACEHOLDER Peerage of Arx"
HOUSE_ORG_NAME = "House Veyrane PLACEHOLDER"
DUCAL_TITLE_NAME = "Duchy of Veyrane PLACEHOLDER"
DOMAIN_NAME = "Veyrane Vale PLACEHOLDER"
CLAIMABLE_TITLE_NAME = "Barony of Thornmere PLACEHOLDER"
CLAIMABLE_DOMAIN_NAME = "Thornmere Marches PLACEHOLDER"
TEMPLATE_NAME = "Arx Barony Charter PLACEHOLDER"

# Founder demo ladder (#3983 Plan B Task 7): an unclaimed duchy chain a
# founder can claim at CG (plus a loose barony inside its own county and a
# sibling county with its own seat), sitting under a Kingdom-tier rung the
# demo house holds — the demo house is the LIEGE here, never the holder of
# the new chain, so the founder ladder lists the duchy claimable under a
# published liege. `OVERLORDSHIP_TITLE_NAME` is the demo house's own
# realm-level rung; the pre-existing `DUCAL_TITLE_NAME` above predates
# `plant_rung` and has no Area chain of its own to hang a vassal duchy off.
OVERLORDSHIP_TITLE_NAME = "Veyrane Overlordship PLACEHOLDER"
DEMO_DUCHY_NAME = "Duchy of Ashgrave PLACEHOLDER"
DEMO_COUNTY_NAME = "County of Millhaven PLACEHOLDER"
CAPITAL_CITY_NAME = "Arx City PLACEHOLDER"


def _ensure_house_charter_anchors(
    realm: Realm,
) -> tuple[Society, OrganizationType, Organization]:
    """Ensure the Crown org, its Society, and both org types exist (idempotent).

    None of these are in ``CONTENT_MODELS`` (#2875): they are plain
    seeder-owned config, but content-repo ``HouseTemplate``/``SuccessionLaw``
    rows can FK the Crown, its Society, and the ``noble_family``/
    ``commoner_family`` org types by name, so all of them must exist before
    the content load resolves those fixtures. Called two ways: once from
    ``world.seeds.config_prerequisites._house_charter_anchors`` (before
    ``load_content_first()``, with its own ``realm`` resolution, a no-op
    there on a database with no "Arx" realm authored yet), and again from
    ``seed_houses_demo`` after the content load, once ``realm`` is actually
    available (the self-healing gameplay-call-site pattern ADR-0171
    describes for a code-required row).

    Returns ``(society, org_type, crown)`` (``org_type`` is ``noble_family``;
    ``commoner_family`` is minted here too but not part of the return shape).
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
    OrganizationType.objects.get_or_create(
        name="commoner_family",
        defaults={
            "rank_1_title": "Head of the Family",
            "rank_2_title": "Elder",
            "rank_3_title": "Family",
            "rank_4_title": "Household",
            "rank_5_title": "Hands",
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
    from django.conf import settings  # noqa: PLC0415

    from world.areas.constants import AreaLevel  # noqa: PLC0415
    from world.areas.models import Area  # noqa: PLC0415
    from world.realms.models import Realm  # noqa: PLC0415
    from world.roster.models import Family  # noqa: PLC0415
    from world.seeds.kinship import DUCAL_HOUSE_NAME, seed_kinship_demo  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415
    from world.societies.houses.almanach import publish_house  # noqa: PLC0415
    from world.societies.houses.constants import (  # noqa: PLC0415
        RecognitionRuleKind,
        SuccessionDerivation,
        SuccessionOrdering,
        TitleTier,
    )
    from world.societies.houses.models import (  # noqa: PLC0415
        HoldingKind,
        HoldingMaterialSource,
        HouseRecognitionRule,
        SuccessionLaw,
        Title,
    )
    from world.societies.houses.services import (  # noqa: PLC0415
        add_holding,
        create_domain,
        swear_fealty,
    )
    from world.societies.models import Organization, Vacancy  # noqa: PLC0415

    seed_kinship_demo()
    seed_nobiliary_particles()
    seed_land_shapes()
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
    _seed_house_creator(realm=realm, society=society, org_type=org_type, crown=crown, law=law)

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
    # Called on every run, not just the first: an existing demo house from an
    # older seed run that predates this call would otherwise stay draft
    # forever (#3983 Plan B Task 7 fold-in). The founder ladder and the demo
    # capital are here for the same reason (#3983 review M3) — both are
    # idempotent by name, and a dev database seeded before this branch would
    # otherwise never get either of them.
    publish_house(house)
    _seed_demo_founder_ladder(realm=realm, house=house)
    _ensure_demo_capital(realm)
    if not created:
        return

    if settings.SEED_SAMPLE_CONTENT and house.family_id is not None:
        Vacancy.objects.get_or_create(
            organization=house,
            name="Household guard PLACEHOLDER",
            defaults={
                "description": "PLACEHOLDER: stands a post, keeps the gate.",
                "importance": 1,
                "presumed_importance": 1,
            },
        )

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
    _seed_material_holdings(
        domain=domain, HoldingKind=HoldingKind, source_model=HoldingMaterialSource
    )

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


def _seed_demo_founder_ladder(*, realm, house) -> None:
    """Plant the founder demo ladder (#3983 Plan B Task 7, idempotent by name).

    One unclaimed duchy chain (duchy, county, seat barony) a founder can
    claim at CG, plus one undefined loose barony inside the duchy's own
    county (`claim_grants` swallows it into a duchy claim, ADR-0315) and one
    unclaimed county with its own seat barony sitting directly under the
    duchy (independently claimable, NOT swallowed by a duchy claim). The
    whole chain plants under `OVERLORDSHIP_TITLE_NAME`, a Kingdom-tier rung
    the demo house holds, so `liege_for_title` walks straight up to the
    house and the founder ladder shows the duchy claimable under a
    published liege.
    """
    from world.societies.houses.almanach import batch_unclaimed, plant_rung  # noqa: PLC0415
    from world.societies.houses.constants import TitleTier  # noqa: PLC0415
    from world.societies.houses.models import Title  # noqa: PLC0415

    overlordship = Title.objects.filter(name=OVERLORDSHIP_TITLE_NAME).first()
    if overlordship is None:
        overlordship = plant_rung(
            realm=realm, tier=TitleTier.KINGDOM, name=OVERLORDSHIP_TITLE_NAME, held_by=house
        )
    if Title.objects.filter(name=DEMO_DUCHY_NAME).exists():
        return
    duchy = plant_rung(
        realm=realm, tier=TitleTier.DUCHY, name=DEMO_DUCHY_NAME, parent_title=overlordship
    )
    duchy_county = Title.objects.get(tier=TitleTier.COUNTY, seat_domain=duchy.seat_domain)
    batch_unclaimed(parent_title=duchy_county, tier=TitleTier.BARONY, count=1)
    plant_rung(realm=realm, tier=TitleTier.COUNTY, name=DEMO_COUNTY_NAME, parent_title=duchy)


def _ensure_demo_capital(realm) -> None:
    """Mark a CITY-level `Area` of `realm` its capital, planting one when
    none exists (#3983 Plan B Task 7). `charter_for_realm`'s `capital_name`,
    the founder Estate leaf's gate (`_validate_kin_and_lands`), and
    `materialize_house_claim`'s `plan_estate` call all read `Area.is_capital`.
    """
    from django.utils.text import slugify  # noqa: PLC0415

    from world.areas.constants import AreaLevel, GridOrigin  # noqa: PLC0415
    from world.areas.models import Area  # noqa: PLC0415

    if Area.objects.filter(realm=realm, is_capital=True).exists():
        return
    city = Area.objects.filter(realm=realm, level=AreaLevel.CITY).first()
    if city is None:
        city = Area.objects.create(
            name=CAPITAL_CITY_NAME,
            slug=slugify(CAPITAL_CITY_NAME),
            level=AreaLevel.CITY,
            realm=realm,
            origin=GridOrigin.AUTHORED,
        )
    city.is_capital = True
    city.save(update_fields=["is_capital"])


def _seed_material_holdings(*, domain, HoldingKind, source_model) -> None:  # noqa: N803
    """Quarry and lumber camp beside the farmland (#696 gap 8): the material
    half of a domain's output, each with one bulk ``HoldingMaterialSource``.

    Categories belong to the crafting seed (``world/seeds/crafting_materials.py``
    owns ``Stone`` and ``Wood``); this seeder only looks them up and skips the
    source row when one is absent, so cluster order never matters here.
    """
    from world.items.constants import MaterialSourceKind  # noqa: PLC0415
    from world.items.models import MaterialCategory  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415
    from world.societies.houses.services import add_holding  # noqa: PLC0415

    stone = MaterialCategory.objects.filter(name="Stone").first()
    timber = MaterialCategory.objects.filter(name="Wood").first()
    for kind_name, description, category in (
        ("Quarry PLACEHOLDER", "PLACEHOLDER: a hillside cut for building stone.", stone),
        ("Lumber camp PLACEHOLDER", "PLACEHOLDER: a woodlot worked for timber.", timber),
    ):
        kind = authored_or_sample(
            HoldingKind,
            {"description": description, "stream_kind": "domain_tax", "base_gross": 400},
            name=kind_name,
        )
        if kind is None:
            continue
        holding = domain.holdings.filter(kind=kind).first() or add_holding(domain=domain, kind=kind)
        if category is None:
            continue
        source_model.objects.get_or_create(
            holding=holding,
            material_category=category,
            defaults={"quality": 1, "source_kind": MaterialSourceKind.BULK},
        )


def _seed_house_creator(*, realm, society, org_type, crown, law) -> None:
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
            "org_type": org_type,
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
