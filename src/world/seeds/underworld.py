"""Criminal underworld demo seed (#2862) — PLACEHOLDER content.

Seeds the first walkable turf-war stage: the ``gang`` OrganizationType (named
in the model docstring since the beginning, never seeded), one NPC gang, one
contested crime neighborhood with a turf position and a CRIME_KICKUP stream,
and the Retaliation crisis type the turf service opens against pushers.
Real placement, prose, and the mission chain ride the content pass.
"""

from __future__ import annotations

GANG_ORG_TYPE_NAME = "gang"
NPC_GANG_NAME = "The Ashfingers PLACEHOLDER"
CRIME_NEIGHBORHOOD_NAME = "Dockside Warrens PLACEHOLDER"
NPC_GANG_STARTING_GRIP = 60
RETALIATION_CRISIS_TYPE_NAME = "Gang Retaliation"
KICKUP_STREAM_NAME = "Warrens kick-up PLACEHOLDER"
KICKUP_GROSS = 2000  # coppers/cycle, PLACEHOLDER


def seed_underworld_demo() -> None:
    """Seed the PLACEHOLDER turf-war stage (idempotent)."""
    _seed_gang_and_turf()
    _seed_retaliation_crisis_type()


def _seed_gang_and_turf() -> None:
    from world.areas.constants import AreaLevel  # noqa: PLC0415
    from world.areas.models import Area  # noqa: PLC0415
    from world.currency.constants import IncomeStreamKind  # noqa: PLC0415
    from world.currency.models import OrgIncomeStream  # noqa: PLC0415
    from world.societies.models import (  # noqa: PLC0415
        NeighborhoodTurf,
        Organization,
        OrganizationType,
    )

    org_type, _created = OrganizationType.objects.get_or_create(name=GANG_ORG_TYPE_NAME)
    gang, _created = Organization.objects.get_or_create(
        name=NPC_GANG_NAME,
        defaults={
            "org_type": org_type,
            "description": (
                "PLACEHOLDER: the crew that runs the Warrens — burn-scarred "
                "knuckles and long memories. NPC-run; push them and see."
            ),
        },
    )
    area, _created = Area.objects.get_or_create(
        name=CRIME_NEIGHBORHOOD_NAME,
        defaults={"level": AreaLevel.NEIGHBORHOOD},
    )
    turf, turf_created = NeighborhoodTurf.objects.get_or_create(
        area=area,
        defaults={"controlling_org": gang, "grip": NPC_GANG_STARTING_GRIP},
    )
    if turf_created:
        from world.societies.turf_services import _sync_crime_modifier  # noqa: PLC0415

        _sync_crime_modifier(turf)
    OrgIncomeStream.objects.get_or_create(
        name=KICKUP_STREAM_NAME,
        defaults={
            "organization": gang,
            "kind": IncomeStreamKind.CRIME_KICKUP,
            "gross_amount": KICKUP_GROSS,
            "area": area,
        },
    )


def _seed_retaliation_crisis_type() -> None:
    """The NPC gang's answer to a turf push — PAY tribute or WAIT and bleed.

    The MISSION option ("Hold the Corner") is bound by the missions content
    seed once the template exists — a typeless option row would be dead
    content, so only PAY/WAIT seed here.
    """
    from world.societies.houses.constants import (  # noqa: PLC0415
        CrisisAudience,
        CrisisResolutionKind,
        CrisisValence,
        DomainCrisisSeverity,
    )
    from world.societies.houses.models import (  # noqa: PLC0415
        DomainCrisisType,
        DomainCrisisTypeOption,
    )

    crisis_type, _created = DomainCrisisType.objects.get_or_create(
        name=RETALIATION_CRISIS_TYPE_NAME,
        defaults={
            "description": (
                "PLACEHOLDER: the crew you pushed pushes back — collectors "
                "leaned on, corners watched, knives shown."
            ),
            "default_severity": DomainCrisisSeverity.TROUBLE,
            "automated": False,
            "valence": CrisisValence.THREAT,
            "audience": CrisisAudience.CRIMINAL_ORG,
        },
    )
    DomainCrisisTypeOption.objects.get_or_create(
        crisis_type=crisis_type,
        kind=CrisisResolutionKind.PAY,
        defaults={"cost_coppers": 5000},
    )
    DomainCrisisTypeOption.objects.get_or_create(
        crisis_type=crisis_type,
        kind=CrisisResolutionKind.WAIT,
        defaults={"self_resolve_pct": 30, "worsen_pct": 30},
    )
