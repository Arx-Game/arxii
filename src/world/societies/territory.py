"""Territory: land units and the base value of held ground (#4060).

The maintainer's rulings (2026-09-28/29):

- Territory is staff-built outdoor rooms and the area rungs above them, never
  buildings or indoor rooms (player-built rooms would mint turf).
- Legitimate control (a ``Domain``) descends from a city's Lord Mayor; criminal
  control (a ``Turf``) ascends from crews. Both may hold the same ground and
  both yield from it.
- Land yields at the LOWEST controlled rung of each kind; a barony's rooms do
  not pay the duchy again, a crew's corner does not pay the gang again. Higher
  rungs earn through fealty tithes (ADR: see docs/adr on territory yield).

Each controlled rung carries one ``OrgIncomeStream`` of kind TERRITORY whose
gross is recomputed every accrual from the rung's land units and its
multiplier (a Domain's prosperity, a Turf's grip). It pools and is collected
like every other stream (ADR-0081): nothing here lands money.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from world.societies.constants import ControlKind

if TYPE_CHECKING:
    from evennia_extensions.models import RoomProfile
    from world.areas.models import Area
    from world.currency.models import OrgIncomeStream
    from world.societies.houses.models import Domain, DomainHolding
    from world.societies.models import Turf

logger = logging.getLogger(__name__)


def outdoor_room_ids_under(area: Area) -> set[int]:
    """Pks of every outdoor room in ``area`` and its subtree: the land units."""
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415
    from world.areas.services import area_subtree_pks  # noqa: PLC0415

    return set(
        RoomProfile.objects.filter(area_id__in=area_subtree_pks(area), is_outdoor=True).values_list(
            "pk", flat=True
        )
    )


def _lower_rung_room_ids(area: Area, kind: str) -> set[int]:
    """Rooms under ``area`` that a lower rung of the same ``kind`` already holds."""
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415
    from world.areas.services import area_subtree_pks  # noqa: PLC0415

    subtree = set(area_subtree_pks(area))
    below = subtree - {area.pk}
    taken: set[int] = set()
    if kind == ControlKind.LEGITIMATE:
        from world.societies.houses.models import Domain  # noqa: PLC0415

        for held in Domain.objects.filter(area_id__in=below, owner_org__isnull=False):
            taken |= outdoor_room_ids_under(held.area)
        return taken
    from world.societies.models import Turf  # noqa: PLC0415

    for held in Turf.objects.filter(area_id__in=below, controlling_org__isnull=False):
        taken |= outdoor_room_ids_under(held.area)
    taken |= set(
        RoomProfile.objects.filter(
            area_id__in=subtree, is_outdoor=True, turf__controlling_org__isnull=False
        ).values_list("pk", flat=True)
    )
    return taken


def territory_units(site: Area | RoomProfile, kind: str) -> int:
    """Land units a controller of ``kind`` earns from at ``site``.

    An outdoor room is one unit (an indoor room none). An area's units are its
    outdoor rooms minus those a lower rung of the same kind holds.
    """
    from world.areas.models import Area  # noqa: PLC0415

    if not isinstance(site, Area):
        return 1 if site.is_outdoor else 0
    return len(outdoor_room_ids_under(site) - _lower_rung_room_ids(site, kind))


def occupied_units(domain: Domain, *, exclude_holding: DomainHolding | None = None) -> int:
    """Land units the domain's sited LAND holdings already occupy (#4060 slice 2)."""
    holdings = domain.holdings.select_related("kind").exclude(room_profile__isnull=True)
    if exclude_holding is not None and exclude_holding.pk is not None:
        holdings = holdings.exclude(pk=exclude_holding.pk)
    return sum(holding.units for holding in holdings)


def free_units(domain: Domain, *, exclude_holding: DomainHolding | None = None) -> int:
    """Units left for a new development: the domain's land minus what stands on it."""
    total = territory_units(domain.area, ControlKind.LEGITIMATE)
    return max(0, total - occupied_units(domain, exclude_holding=exclude_holding))


def _stream_name(site_name: str) -> str:
    return f"{site_name}: territory"[:100]


def ensure_turf_stream(turf: Turf) -> OrgIncomeStream | None:
    """Give a held turf its TERRITORY stream, or retarget the one it has."""
    from world.currency.constants import IncomeStreamKind  # noqa: PLC0415
    from world.currency.models import OrgIncomeStream  # noqa: PLC0415

    if turf.controlling_org_id is None:
        return turf.income_stream
    stream = turf.income_stream
    if stream is None:
        stream = OrgIncomeStream.objects.create(
            organization=turf.controlling_org,
            name=_stream_name(turf.site_name),
            kind=IncomeStreamKind.TERRITORY,
            gross_amount=0,
            area=turf.area,
            room_profile=turf.room_profile,
        )
        turf.income_stream = stream
        turf.save(update_fields=["income_stream"])
    elif stream.organization_id != turf.controlling_org_id:
        stream.organization = turf.controlling_org
        stream.save(update_fields=["organization"])
    return stream


def ensure_domain_stream(domain: Domain) -> OrgIncomeStream | None:
    """Give an owned domain its TERRITORY stream, or retarget the one it has."""
    from world.currency.constants import IncomeStreamKind  # noqa: PLC0415
    from world.currency.models import OrgIncomeStream  # noqa: PLC0415

    if domain.owner_org_id is None:
        return domain.territory_stream
    stream = domain.territory_stream
    if stream is None:
        stream = OrgIncomeStream.objects.create(
            organization=domain.owner_org,
            name=_stream_name(domain.name or domain.area.name),
            kind=IncomeStreamKind.TERRITORY,
            gross_amount=0,
            area=domain.area,
        )
        domain.territory_stream = stream
        domain.save(update_fields=["territory_stream"])
    elif stream.organization_id != domain.owner_org_id:
        stream.organization = domain.owner_org
        stream.save(update_fields=["organization"])
    return stream


def ensure_territory_streams() -> int:
    """Every held rung has its TERRITORY stream (idempotent; the weekly phase's first step).

    Runs before income accrual so a domain planted or a turf taken during the
    week pools from its first full cycle, and so rungs that predate #4060 need
    no backfill migration.
    """
    from world.societies.houses.models import Domain  # noqa: PLC0415
    from world.societies.models import Turf  # noqa: PLC0415

    count = 0
    for domain in Domain.objects.filter(owner_org__isnull=False).select_related(
        "territory_stream", "owner_org", "area"
    ):
        ensure_domain_stream(domain)
        count += 1
    for turf in Turf.objects.filter(controlling_org__isnull=False).select_related(
        "income_stream", "controlling_org", "area", "room_profile"
    ):
        ensure_turf_stream(turf)
        count += 1
    return count


def territory_gross(stream: OrgIncomeStream) -> int:
    """This cycle's gross for a TERRITORY stream: units x base x the rung's multiplier."""
    from world.currency.constants import TERRITORY_BASE_PER_UNIT  # noqa: PLC0415
    from world.societies.turf_services import GRIP_MAX  # noqa: PLC0415

    domain = stream.territory_domain_or_none
    if domain is not None:
        # Developments use up the land they stand on (#4060 slice 2): a farm's
        # units pay through the farm's own stream, not the base rate as well.
        return int(free_units(domain) * TERRITORY_BASE_PER_UNIT * domain.income_multiplier)
    turf = stream.turf_or_none
    if turf is not None:
        units = territory_units(turf.site, ControlKind.CRIMINAL)
        return units * TERRITORY_BASE_PER_UNIT * turf.grip // GRIP_MAX
    logger.warning("TERRITORY stream %s is anchored to no Domain or Turf; earns nothing", stream.pk)
    return 0
