"""Neighborhood turf control (#2862): grip, pushes, flips, and consequences.

The state layer the gang-turf project machinery (built in #2418, orphaned
since) finally moves. One service owns the arithmetic:

- ``apply_turf_push(org, area, amount)`` — a completed turf-project tier or
  a turf mission's PROJECT line pushes: the controller's own pushes deepen
  grip; a rival's erode it; grip breaking flips control.
- Control writes the world: the area's ``StatKey.CRIME`` cascade modifier
  tracks grip (the dead stat gets its writer), and the area's CRIME_KICKUP
  income streams re-target to the controller — holding the neighborhood IS
  the revenue and (via authored AreaLaw posture, a content pass) the safety.
- A push against held ground provokes: the NPC gang answers through the
  crisis engine (a Retaliation THREAT against the pushing org).

Magnitudes PLACEHOLDER throughout (#2862 author pass).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.areas.models import Area
    from world.societies.models import NeighborhoodTurf, Organization

logger = logging.getLogger(__name__)

GRIP_MAX = 100
# A flip starts the new controller shallow — freshly taken ground is loose.
FLIP_START_GRIP = 25
# Area CRIME modifier value = grip // CRIME_GRIP_DIVISOR (0-50 band).
CRIME_GRIP_DIVISOR = 2
TURF_CRIME_SOURCE = "neighborhood_turf"
RETALIATION_CRISIS_TYPE_NAME = "Gang Retaliation"


def apply_turf_push(organization: Organization, area: Area, amount: int) -> NeighborhoodTurf:
    """Apply a turf push by *organization* against/into *area* (#2862)."""
    from world.societies.models import NeighborhoodTurf  # noqa: PLC0415

    turf, _created = NeighborhoodTurf.objects.get_or_create(area=area)
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
    _retarget_kickup_streams(turf)
    if provoked:
        _open_retaliation(organization, turf, previous_holder)
    return turf


def _sync_crime_modifier(turf: NeighborhoodTurf) -> None:
    """The area-wide CRIME cascade row tracks grip — the dead stat's writer."""
    from world.locations.constants import (  # noqa: PLC0415
        KeyType,
        LocationParentType,
        StatKey,
    )
    from world.locations.models import LocationValueModifier  # noqa: PLC0415

    value = turf.grip // CRIME_GRIP_DIVISOR
    LocationValueModifier.objects.update_or_create(
        parent_type=LocationParentType.AREA,
        area=turf.area,
        room_profile=None,
        key_type=KeyType.STAT,
        stat_key=StatKey.CRIME,
        source=TURF_CRIME_SOURCE,
        defaults={"value": value, "change_per_day": 0},
    )


def _retarget_kickup_streams(turf: NeighborhoodTurf) -> None:
    """The neighborhood's crime kick-up flows to whoever holds it."""
    from world.currency.constants import IncomeStreamKind  # noqa: PLC0415
    from world.currency.models import OrgIncomeStream  # noqa: PLC0415

    if turf.controlling_org_id is None:
        return
    # Per-row save, not bulk .update() — SharedMemoryModel's identity map
    # would serve stale cached instances after a queryset update.
    streams = OrgIncomeStream.objects.filter(
        area=turf.area,
        kind=IncomeStreamKind.CRIME_KICKUP,
    ).exclude(organization_id=turf.controlling_org_id)
    for stream in streams:
        stream.organization = turf.controlling_org
        stream.save(update_fields=["organization"])


def _open_retaliation(
    pushing_org: Organization,
    turf: NeighborhoodTurf,
    previous_holder: Organization | None,
) -> None:
    """A push against held ground provokes the holder — via the crisis engine.

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
            f"PLACEHOLDER: {holder_name} answers the push into {turf.area.name} — knives out."
        ),
    )
