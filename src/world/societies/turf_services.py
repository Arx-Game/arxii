"""Turf control (#2862; every rung #4060): grip, pushes, flips, and consequences.

The state layer the gang-turf project machinery (built in #2418, orphaned
since) finally moves. One service owns the arithmetic:

- ``apply_turf_push(org, site, amount)`` - a completed turf-project tier or
  a turf mission's PROJECT line pushes: the controller's own pushes deepen
  grip; a rival's erode it; grip breaking flips control. ``site`` is an
  outdoor ``RoomProfile`` (a crew's corner) or an ``Area`` at NEIGHBORHOOD,
  WARD or BARONY level.
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
    from world.societies.constants import LevyKind  # noqa: PLC0415

    if turf.controlling_org_id is None:
        return
    streams = OrgIncomeStream.objects.filter(
        area=turf.area,
        room_profile=turf.room_profile,
        kind__in=(
            IncomeStreamKind.CRIME_KICKUP,
            IncomeStreamKind.TERRITORY,
            IncomeStreamKind.LEVY,
        ),
    ).exclude(organization_id=turf.controlling_org_id)
    # The legitimate ladder's streams on the same rung (a domain's own TERRITORY
    # stream, a TAX levy) never follow a turf flip.
    for stream in streams:
        if stream.territory_domain_or_none is not None:
            continue
        levy = stream.levy_or_none
        if levy is not None and levy.kind != LevyKind.PROTECTION:
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


# ---------------------------------------------------------------------------
# #4239: staff authoring of the crime ladder from the Almanach. Entry points
# over the push arithmetic above; nothing here lands money or flips a rival.
# ---------------------------------------------------------------------------

GANG_ORG_TYPE_NAME = "gang"


class TurfAuthoringError(ValueError):
    """A refusal with a player-safe message, the shape the Almanach actions relay."""

    def __init__(self, message: str, *, user_message: str) -> None:
        super().__init__(message)
        self.user_message = user_message


def claim_ward(*, organization: Organization, area: Area) -> Turf:
    """Give ``organization`` a ward (or a city) outright, at full grip (#4239).

    Staff authoring, not a push: contested or rival-held ground refuses, so a
    flip is never a side effect of filling in a page.
    """
    from world.areas.constants import AreaLevel  # noqa: PLC0415
    from world.societies.models import Turf  # noqa: PLC0415

    if area.level not in (AreaLevel.WARD, AreaLevel.BARONY):
        msg = f"area {area.pk} is level {area.level}, not a ward"
        raise TurfAuthoringError(msg, user_message="A family's turf is a ward or a city.")
    held = Turf.objects.filter(area=area).exclude(controlling_org__isnull=True).first()
    if held is not None and held.controlling_org_id != organization.pk:
        msg = f"area {area.pk} held by org {held.controlling_org_id}"
        raise TurfAuthoringError(msg, user_message="Somebody already holds that ground.")
    return apply_turf_push(organization, area, GRIP_MAX)


def _under(area: Area, ancestors: set[int]) -> bool:
    node = area
    seen = 0
    while node is not None and seen < 12:  # noqa: PLR2004 - defensive walk cap
        if node.pk in ancestors:
            return True
        node = node.parent
        seen += 1
    return False


def add_gang(
    *,
    family_org: Organization,
    name: str,
    neighborhood: Area,
) -> Organization:
    """A gang beneath a crime family: its organization, its oath, its ground (#4239).

    The gang is an Organization of the gang type under ``family_org``
    (``parent_org`` and a FealtyEdge, the way a vassal house hangs under a
    liege), with a rank ladder, holding ``neighborhood`` at full grip. When
    the family holds a ward, the neighborhood must lie under it.
    """
    from django.db import transaction  # noqa: PLC0415

    from world.areas.constants import AreaLevel  # noqa: PLC0415
    from world.societies.houses.services import HousesServiceError, swear_fealty  # noqa: PLC0415
    from world.societies.membership_services import ensure_default_rank_ladder  # noqa: PLC0415
    from world.societies.models import Organization, OrganizationType, Turf  # noqa: PLC0415

    name = (name or "").strip()
    if not name:
        msg = "blank gang name"
        raise TurfAuthoringError(msg, user_message="A gang needs a name.")
    if neighborhood.level != AreaLevel.NEIGHBORHOOD:
        msg = f"area {neighborhood.pk} is not a neighborhood"
        raise TurfAuthoringError(msg, user_message="A gang's ground is a neighborhood.")
    wards = set(
        Turf.objects.filter(controlling_org=family_org, area__isnull=False).values_list(
            "area_id", flat=True
        )
    )
    if wards and not _under(neighborhood, wards):
        msg = f"neighborhood {neighborhood.pk} outside the family's wards"
        raise TurfAuthoringError(
            msg, user_message="That neighborhood is not in any ward this family holds."
        )
    gang_type = OrganizationType.objects.filter(name=GANG_ORG_TYPE_NAME).first()
    if gang_type is None:
        msg = "no gang org type"
        raise TurfAuthoringError(msg, user_message="The gang organization type is not seeded.")
    with transaction.atomic():
        gang = Organization.objects.create(
            name=name, org_type=gang_type, parent_org=family_org, society=family_org.society
        )
        ensure_default_rank_ladder(gang)
        try:
            swear_fealty(vassal=gang, liege=family_org)
        except HousesServiceError as exc:
            raise TurfAuthoringError(str(exc), user_message=exc.user_message) from exc
        apply_turf_push(gang, neighborhood, GRIP_MAX)
    return gang
