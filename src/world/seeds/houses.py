"""Houses demo seed (#1884) — the kinship demo house made a landed peer.

PLACEHOLDER content. Idempotent get-or-create keyed on names. Rides the
kinship cluster's House Veyrane: gives it an Organization, a nobiliary
particle, realm recognition rules, a succession law, a liege (the seed
crown), a ducal title seated on a domain, and one working holding feeding
the org books — enough to walk the house page, sheet/house, succession
derivation, and the feed on a dev DB.
"""

from __future__ import annotations

CROWN_ORG_NAME = "The Crown of Arx PLACEHOLDER"
HOUSE_ORG_NAME = "House Veyrane PLACEHOLDER"
DUCAL_TITLE_NAME = "Duchy of Veyrane PLACEHOLDER"
DOMAIN_NAME = "Veyrane Vale PLACEHOLDER"
CLAIMABLE_TITLE_NAME = "Barony of Thornmere PLACEHOLDER"
CLAIMABLE_DOMAIN_NAME = "Thornmere Marches PLACEHOLDER"
TEMPLATE_NAME = "Arx Barony Charter PLACEHOLDER"


def seed_houses_demo() -> None:
    """Seed the PLACEHOLDER landed house (idempotent)."""
    from world.areas.constants import AreaLevel  # noqa: PLC0415
    from world.areas.models import Area  # noqa: PLC0415
    from world.realms.models import Realm  # noqa: PLC0415
    from world.roster.models import Family  # noqa: PLC0415
    from world.seeds.kinship import DUCAL_HOUSE_NAME, seed_kinship_demo  # noqa: PLC0415
    from world.societies.houses.constants import (  # noqa: PLC0415
        RecognitionRuleKind,
        SuccessionDerivation,
        SuccessionOrdering,
        TitleTier,
    )
    from world.societies.houses.models import (  # noqa: PLC0415
        HoldingKind,
        HouseRecognitionRule,
        NobiliaryParticle,
        SuccessionLaw,
        Title,
    )
    from world.societies.houses.services import (  # noqa: PLC0415
        add_holding,
        create_domain,
        swear_fealty,
    )
    from world.societies.models import Organization, OrganizationType, Society  # noqa: PLC0415

    seed_kinship_demo()
    family = Family.objects.get(name=DUCAL_HOUSE_NAME)

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
    crown, _ = Organization.objects.get_or_create(
        name=CROWN_ORG_NAME,
        defaults={
            "description": "PLACEHOLDER: the throne all fealty flows toward.",
            "society": society,
            "org_type": org_type,
        },
    )
    law, _ = SuccessionLaw.objects.get_or_create(
        name="Veyrane Primogeniture PLACEHOLDER",
        defaults={
            "derivation": SuccessionDerivation.PRIMOGENITURE_WEDLOCK,
            "ordering_rule": SuccessionOrdering.ELDEST,
            "require_wedlock": True,
        },
    )
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

    NobiliaryParticle.objects.get_or_create(
        realm=realm,
        family_type=Family.FamilyType.NOBLE,
        defaults={"particle": "du"},
    )
    for kind in (
        RecognitionRuleKind.MATRILINEAL_AUTO_WEDLOCK,
        RecognitionRuleKind.MOTHER_OPTION_OUT_OF_WEDLOCK,
    ):
        HouseRecognitionRule.objects.get_or_create(realm=realm, kind=kind)

    swear_fealty(vassal=house, liege=crown)

    area, _ = Area.objects.get_or_create(name=DOMAIN_NAME, defaults={"level": AreaLevel.REGION})
    domain = create_domain(area=area, name=DOMAIN_NAME, owner_org=house)
    farmland, _ = HoldingKind.objects.get_or_create(
        name="Farmland PLACEHOLDER",
        defaults={
            "description": "PLACEHOLDER: grain terraces and tenant farms.",
            "stream_kind": "domain_tax",
            "base_gross": 1000,
        },
    )
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
    from world.roster.models import Family  # noqa: PLC0415
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

    farmland, _ = HoldingKind.objects.get_or_create(
        name="Farmland PLACEHOLDER",
        defaults={
            "description": "PLACEHOLDER: grain terraces and tenant farms.",
            "stream_kind": "domain_tax",
            "base_gross": 1000,
        },
    )
    template, _ = HouseTemplate.objects.get_or_create(
        name=TEMPLATE_NAME,
        defaults={
            "description": "PLACEHOLDER: the standard charter for a landed barony of Arx.",
            "realm": realm,
            "family_type": Family.FamilyType.NOBLE,
            "society": society,
            "liege": crown,
            "default_succession_law": law,
        },
    )
    template.holdings.add(farmland)

    # #2079 — one exemplar aspect definition + feature proving the loop;
    # real regional catalogs arrive from the per-region content brainstorms.
    virtue, _ = HouseAspectDefinition.objects.get_or_create(
        name="House Virtue PLACEHOLDER",
        defaults={"prompt": "PLACEHOLDER: which virtue did your house cling to?"},
    )
    for order, (option_name, blurb) in enumerate(
        [
            ("Fortitude PLACEHOLDER", "PLACEHOLDER: endurance without breaking."),
            ("Candor PLACEHOLDER", "PLACEHOLDER: truth spoken plainly."),
            ("Charity PLACEHOLDER", "PLACEHOLDER: the open hand."),
        ]
    ):
        HouseAspectOption.objects.get_or_create(
            definition=virtue,
            name=option_name,
            defaults={"description": blurb, "display_order": order},
        )
    hearth, _ = HouseFeature.objects.get_or_create(
        slug="hearth-right-placeholder",
        defaults={
            "name": "Hearth Right PLACEHOLDER",
            "description": "PLACEHOLDER: guests under the house's roof are sacrosanct.",
        },
    )
    template.aspect_definitions.add(virtue)
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
