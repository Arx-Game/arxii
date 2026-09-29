"""Crew slots: the crime ladder's claimable corners (#4061 slice 3).

Maintainer ruling (2026-09-29): a crew is taken much like a barony title. A
gang marks which rooms under its neighborhood are crew turf; an unclaimed slot
(its room or few rooms, the gang as liege) is authored by staff, and the player
takes it at character creation by naming a crew. The claim creates the crew's
Turf on those rooms and its fealty to the gang; the slot's gang is the liege,
so no open-liege choice exists.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

if TYPE_CHECKING:
    from world.areas.models import Area
    from world.realms.models import Realm
    from world.societies.models import CrewSlot, Organization

logger = logging.getLogger(__name__)

CREW_START_GRIP = 30  # a freshly claimed corner is loosely held; PLACEHOLDER


class CrewSlotError(ValueError):
    def __init__(self, message: str, *, user_message: str) -> None:
        super().__init__(message)
        self.user_message = user_message


def _area_realm(area: Area | None) -> Realm | None:
    node = area
    seen = 0
    while node is not None and seen < 10:  # noqa: PLR2004 - defensive walk cap
        if node.realm_id is not None:
            return node.realm
        node = node.parent
        seen += 1
    return None


def open_crew_slots(*, realm: Realm | None = None) -> list[CrewSlot]:
    """Active, unclaimed slots; in ``realm`` (by their rooms' areas) when given."""
    from world.societies.models import CrewSlot  # noqa: PLC0415

    slots = CrewSlot.objects.filter(is_active=True, claimed_by__isnull=True).select_related("gang")
    found: list[CrewSlot] = []
    for slot in slots:
        rooms = list(slot.rooms.all())
        if not rooms:
            continue
        if realm is not None and _area_realm(rooms[0].area) != realm:
            continue
        found.append(slot)
    return found


@transaction.atomic
def claim_crew_slot(slot: CrewSlot, org: Organization) -> CrewSlot:
    """``org`` takes the corner: Turf on each room, fealty to the gang, the slot closed."""
    from world.societies.houses.services import swear_fealty  # noqa: PLC0415
    from world.societies.models import Turf  # noqa: PLC0415
    from world.societies.territory import ensure_turf_stream  # noqa: PLC0415
    from world.societies.turf_services import (  # noqa: PLC0415
        _sync_crime_modifier,
        retarget_territory_streams,
    )

    if not slot.is_open:
        msg = f"crew slot {slot.pk} is not open"
        raise CrewSlotError(msg, user_message="That corner is already somebody's.")
    for room in slot.rooms.all():
        turf, _created = Turf.objects.get_or_create(room_profile=room, area=None)
        turf.controlling_org = org
        turf.grip = max(turf.grip, CREW_START_GRIP)
        turf.save(update_fields=["controlling_org", "grip", "updated_at"])
        _sync_crime_modifier(turf)
        ensure_turf_stream(turf)
        retarget_territory_streams(turf)
    swear_fealty(vassal=org, liege=slot.gang)
    slot.claimed_by = org
    slot.claimed_at = timezone.now()
    slot.save(update_fields=["claimed_by", "claimed_at"])
    logger.info("crew slot %s claimed by %s", slot.pk, org.name)
    return slot
