"""Ship sanctum bonus + level-3 capability read (#1832 Task 5).

A ship's persistent stat bonus and unlocked capabilities are derived from the
woven SANCTUM threads on the ship's sanctum room, if it has one. A ship has at
most one sanctum room for MVP.
"""

from __future__ import annotations

from django.db.models import Sum

from world.magic.models import Resonance, SanctumDetails, Thread
from world.ships.models import ShipDetails
from world.ships.types import ShipStatBonus


def _sanctum_for_ship(ship: ShipDetails) -> SanctumDetails | None:
    """Return the active ``SanctumDetails`` installed on one of the ship's rooms.

    Mirrors the filter style of ``sanctum_in_room``
    (``actions/definitions/sanctum.py``): the ship's rooms are the
    ``RoomProfile``s whose ``area`` matches the ship's backing ``Building``'s
    area. A ship has at most one sanctum room for MVP.
    """
    return SanctumDetails.objects.filter(
        feature_instance__room_profile__area=ship.building.area,
        feature_instance__dissolved_at__isnull=True,
    ).first()


def ship_sanctum_bonus(ship: ShipDetails) -> ShipStatBonus:
    """Sum active woven SANCTUM thread levels into a ``ShipStatBonus``.

    PLACEHOLDER mapping: ``hull = handling = armament = total_levels`` — a
    per-resonance split is a later content pass. Returns ``ShipStatBonus()``
    (all zeros) when the ship has no sanctum or no active woven threads.
    """
    sanctum = _sanctum_for_ship(ship)
    if sanctum is None:
        return ShipStatBonus()

    total_levels = (
        Thread.objects.filter(
            target_sanctum_details=sanctum,
            retired_at__isnull=True,
        ).aggregate(total=Sum("level"))["total"]
        or 0
    )
    if not total_levels:
        return ShipStatBonus()

    return ShipStatBonus(hull=total_levels, handling=total_levels, armament=total_levels)


def ship_sanctum_capabilities(ship: ShipDetails) -> list[Resonance]:
    """Return the distinct resonances of woven SANCTUM threads at level >= 3.

    Each such resonance maps to an authored ``ThreadPullEffect`` with
    ``min_thread_level=3`` used as the capability source. Empty list when the
    ship has no sanctum or no thread has reached level 3.
    """
    sanctum = _sanctum_for_ship(ship)
    if sanctum is None:
        return []

    resonance_ids = (
        Thread.objects.filter(
            target_sanctum_details=sanctum,
            retired_at__isnull=True,
            level__gte=3,
        )
        .values_list("resonance_id", flat=True)
        .distinct()
    )
    if not resonance_ids:
        return []

    return list(Resonance.objects.filter(pk__in=resonance_ids))
