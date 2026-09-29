"""Turf control (#2862; every rung #4060): grip, pushes, flips, and consequences.

The state layer the gang-turf project machinery (built in #2418, orphaned
since) finally moves. One service owns the arithmetic:

- ``apply_turf_push(org, site, amount)`` - a completed turf-project tier or
  a turf mission's PROJECT line pushes: the controller's own pushes deepen
  grip; a rival's erode it; grip breaking flips control. ``site`` is an
  outdoor ``RoomProfile`` (a crew's corner) or an ``Area`` at NEIGHBORHOOD,
  WARD or CITY level.
- Control writes the world: the site's ``StatKey.CRIME`` cascade modifier
  tracks grip (a room's row for a room, the area's row for an area; the
  rollup sums every rung above a room), the site's CRIME_KICKUP income
  streams re-target to the controller, and the site's TERRITORY stream (the
  base value of the ground, ``world.societies.territory``) follows control.
- A push against held ground provokes: the NPC gang answers through the
  crisis engine (a Retaliation THREAT against the pushing org).

Magnitudes PLACEHOLDER throughout (#2862 author pass).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia_extensions.models import RoomProfile
    from world.areas.models import Area
    from world.societies.models import Organization, Turf

logger = logging.getLogger(__name__)

GRIP_MAX = 100
FLIP_START_GRIP = 25
CRIME_GRIP_DIVISOR = 2
TURF_CRIME_SOURCE = "neighborhood_turf"
RETALIATION_CRISIS_TYPE_NAME = "Gang Retaliation"


def _site_lookup(site: Area | RoomProfile) -> dict:
    from world.areas.models import Area  # noqa: PLC0415

    if isinstance(site, Area):
        return {"area": site, "room_profile": None}
    return {"area": None, "room_profile": site}


def apply_turf_push(organization: Organization, site: Area | RoomProfile, amount: int) -> Turf:
    """Apply a turf push by *organization* against/into *site* (#2862, #4060)."""
    from world.societies.models import Turf  # noqa: PLC0415
    from world.societies.territory import ensure_turf_stream  # noqa: PLC0415

    turf, created = Turf.objects.get_or_create(**_site_lookup(site))
    if created:
        turf.full_clean()
    if amount <= 0:
        return turf

    previous_holder = turf.controlling_org
    provoked = False
    if turf.controlling_org_id is None:
        turf.controlling_org = organization
        turf.grip = min(GRIP_MAX, amount)
    elif turf.controlling_org_id == organization.pk:
        turf.grip = min(GRIP_MAX, turf.grip + amount)
    else:
        provoked = True
        remaining = turf.grip - amount
        if remaining > 0:
            turf.grip = remaining
        else:
            turf.controlling_org = organization
            turf.grip = FLIP_START_GRIP
    turf.save(update_fields=["controlling_org", "grip", "updated_at"])

    _sync_crime_modifier(turf)
    ensure_turf_stream(turf)
    retarget_territory_streams(turf)
    if provoked:
        _open_retaliation(organization, turf, previous_holder)
    return turf


def _sync_crime_modifier(turf: Turf) -> None:
    """The site's CRIME cascade row tracks grip - the dead stat's writer.

    A room turf writes the room's own row and an area turf the area's; the
    per-room resolve and ``area_stat_total`` each sum every rung above, so a
    corner under a crew, a gang and a family reads all three (#4060).
    """
    from world.locations.constants import (  # noqa: PLC0415
        KeyType,
        LocationParentType,
        StatKey,
    )
    from world.locations.models import LocationValueModifier  # noqa: PLC0415

    value = turf.grip // CRIME_GRIP_DIVISOR
    parent_type = LocationParentType.AREA if turf.area_id else LocationParentType.ROOM
    LocationValueModifier.objects.update_or_create(
        parent_type=parent_type,
        area=turf.area,
        room_profile=turf.room_profile,
        key_type=KeyType.STAT,
        stat_key=StatKey.CRIME,
        source=TURF_CRIME_SOURCE,
        defaults={"value": value, "change_per_day": 0},
    )


def retarget_territory_streams(turf: Turf) -> None:
    """The site's crime kick-up and its territory stream flow to whoever holds it."""
    from world.currency.constants import IncomeStreamKind  # noqa: PLC0415
    from world.currency.models import OrgIncomeStream  # noqa: PLC0415

    if turf.controlling_org_id is None:
        return
    streams = OrgIncomeStream.objects.filter(
        area=turf.area,
        room_profile=turf.room_profile,
        kind__in=(IncomeStreamKind.CRIME_KICKUP, IncomeStreamKind.TERRITORY),
    ).exclude(organization_id=turf.controlling_org_id)
    # The domain's own TERRITORY stream on the same area belongs to the
    # legitimate ladder and never follows a turf flip.
    for stream in streams:
        if stream.territory_domain_or_none is not None:
            continue
        stream.organization = turf.controlling_org
        stream.save(update_fields=["organization"])


def _open_retaliation(
    pushing_org: Organization,
    turf: Turf,
    previous_holder: Organization | None,
) -> None:
    """A push against held ground provokes the holder - via the crisis engine.

    Opens (at most one at a time, the engine's one-open rule) a Retaliation
    THREAT against the pushing org. Fail-soft: no seeded type, no crisis.
    """
    from world.societies.houses.constants import CrisisOrigin  # noqa: PLC0415
    from world.societies.houses.crisis_services import open_crisis  # noqa: PLC0415
    from world.societies.houses.models import DomainCrisisType  # noqa: PLC0415

    crisis_type = DomainCrisisType.objects.filter(name=RETALIATION_CRISIS_TYPE_NAME).first()
    if crisis_type is None:
        logger.info("No Retaliation crisis type seeded; turf push goes unanswered.")
        return
    holder_name = previous_holder.name if previous_holder is not None else "the old crew"
    open_crisis(
        org=pushing_org,
        origin=CrisisOrigin.AMBIENT,
        crisis_type=crisis_type,
        description=(
            f"PLACEHOLDER: {holder_name} answers the push into {turf.site_name} - knives out."
        ),
    )
