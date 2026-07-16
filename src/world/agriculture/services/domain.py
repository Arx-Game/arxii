"""Domain resolution and capacity helpers for the agriculture system."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import OperationalError, ProgrammingError

if TYPE_CHECKING:
    from world.room_features.models import RoomFeatureInstance
    from world.societies.houses.models import Domain


def _ancestor_area_ids(area) -> set[int]:
    """Return the set of area ids that are ancestors of (or equal to) ``area``.

    Uses the ``AreaClosure`` materialized view on Postgres. On SQLite
    (where the view doesn't exist), falls back to walking
    ``Area.parent`` manually.
    """
    from world.areas.models import AreaClosure  # noqa: PLC0415

    try:
        ancestor_ids = set(
            AreaClosure.objects.filter(descendant_id=area.pk).values_list("ancestor_id", flat=True)
        )
    except (OperationalError, ProgrammingError):
        # SQLite test fallback (AreaClosure matview missing): walk the parent chain.
        ancestor_ids = set()
        current = area
        while current is not None:
            ancestor_ids.add(current.pk)
            current = current.parent
    ancestor_ids.add(area.pk)
    return ancestor_ids


def resolve_domain_for_feature(
    room_feature_instance: RoomFeatureInstance,
) -> Domain | None:
    """Walk the Area parent chain to find the Domain for a room feature.

    Uses ``RoomProfile.area`` (direct FK) and the ``AreaClosure`` view
    for ancestor walks. Returns the ``Domain`` whose ``area`` is an
    ancestor of the feature's room's area, or ``None`` if no domain is
    found.
    """
    from world.societies.houses.models import Domain  # noqa: PLC0415

    room_area = room_feature_instance.room_profile.area
    if room_area is None:
        return None

    ancestor_ids = _ancestor_area_ids(room_area)
    return Domain.objects.filter(area_id__in=ancestor_ids).first()


def max_food_capacity(domain: Domain) -> int:
    """Sum the capacity contribution of all active Granaries in the domain.

    Walks the domain's area subtree (via AreaClosure) to find all
    RoomFeatureInstance rows with ``service_strategy=GRANARY`` and sums
    ``instance.level × config.granary_capacity_per_level``. Returns 0 if
    no Granaries exist.
    """
    from world.agriculture.services.production import get_food_config  # noqa: PLC0415
    from world.areas.models import AreaClosure  # noqa: PLC0415
    from world.room_features.constants import RoomFeatureServiceStrategy  # noqa: PLC0415
    from world.room_features.models import RoomFeatureInstance  # noqa: PLC0415

    config = get_food_config()

    domain_area = domain.area

    # Find all descendant areas of the domain's area (including itself).
    try:
        descendant_ids = set(
            AreaClosure.objects.filter(ancestor_id=domain_area.pk).values_list(
                "descendant_id", flat=True
            )
        )
    except (OperationalError, ProgrammingError):
        # SQLite test fallback: no descendants table — just use the area itself.
        descendant_ids = {domain_area.pk}
    descendant_ids.add(domain_area.pk)

    granaries = RoomFeatureInstance.objects.active().filter(
        feature_kind__service_strategy=RoomFeatureServiceStrategy.GRANARY,
        room_profile__area_id__in=descendant_ids,
    )
    return sum(g.level * config.granary_capacity_per_level for g in granaries)
