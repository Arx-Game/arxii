"""Phase D — Dwellings polish services (#676).

Polish-add hooks + per-persona prestige_from_dwellings recompute.

Flow:

* ``apply_project_completion(building, template, *, source_project=None)``
  is called by project resolution code when a polish-adding Project
  succeeds on a building. It snapshots the template into a
  ``BuildingProjectInstance``, adds the per-category polish to the
  building's ``BuildingPolish`` totals, and recomputes
  ``prestige_from_dwellings`` for everyone affected (owner; tenants of
  rooms in the building).

* ``apply_room_polish_delta(room, category, delta)`` is the lower-level
  hook used by Phase F (item-placement / removal) to bump room polish
  up or down. Polish never goes negative; deltas are clamped at 0.

* ``recompute_persona_prestige_from_dwellings(persona)`` reads
  building + room polish totals into the persona's
  ``prestige_from_dwellings`` field (and updates total_prestige).

* ``derive_tier_label(category, value)`` returns the highest tier name
  whose ``min_value`` is ≤ ``value``, or None when no thresholds match.

Loop-safety: prestige_from_dwellings is a readout. It never feeds back
into building/room polish.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.db.models import Sum

from world.buildings.models import (
    Building,
    BuildingPolish,
    BuildingProjectInstance,
    BuildingProjectInstancePolish,
    PolishCategory,
    ProjectTemplate,
    RoomPolish,
    TierThreshold,
)

logger = logging.getLogger(__name__)


def derive_tier_label(category: PolishCategory, value: int) -> str | None:
    """Return the highest tier label whose min_value ≤ value, else None.

    Uses the TierThreshold table (``ordering=["category", "-min_value"]``)
    so the first matching row is the highest applicable tier. None when
    no thresholds are authored for this category.
    """
    threshold = (
        TierThreshold.objects.filter(category=category, min_value__lte=value)
        .order_by("-min_value")
        .first()
    )
    return threshold.tier_name if threshold else None


@transaction.atomic
def apply_project_completion(
    building,
    template: ProjectTemplate,
    *,
    source_project=None,
) -> BuildingProjectInstance:
    """Snapshot a completed polish template onto a building.

    Creates the BuildingProjectInstance + per-category instance polish
    rows + bumps the building's aggregate BuildingPolish totals, then
    recomputes prestige_from_dwellings for the owner persona.

    Idempotency: when ``source_project`` is provided, the OneToOne
    constraint on ``BuildingProjectInstance.source_project`` catches a
    duplicate completion at the DB level; the in-Python check below
    raises before that ever fires.
    """
    if (
        source_project is not None
        and BuildingProjectInstance.objects.filter(source_project=source_project).exists()
    ):
        msg = (
            f"apply_project_completion: project {source_project.pk} already has a "
            f"BuildingProjectInstance — refusing to double-apply."
        )
        raise ValueError(msg)

    instance = BuildingProjectInstance.objects.create(
        building=building,
        template=template,
        source_project=source_project,
        weekly_upkeep_cost=template.weekly_upkeep_cost,
        decay_priority=template.decay_priority,
    )

    increments = list(template.polish_increment_rows.select_related("category"))
    for row in increments:
        BuildingProjectInstancePolish.objects.create(
            instance=instance,
            category=row.category,
            value=row.value,
        )
        bp, _created = BuildingPolish.objects.get_or_create(
            building=building,
            category=row.category,
            defaults={"value": 0},
        )
        bp.value = bp.value + row.value
        bp.save(update_fields=["value"])

    if building.owner_persona_id is not None:
        recompute_persona_prestige_from_dwellings(building.owner_persona)

    return instance


@transaction.atomic
def apply_room_polish_delta(
    room,
    category: PolishCategory,
    delta: int,
) -> int:
    """Add ``delta`` polish to a (room, category) pair, clamped at 0.

    Returns the new ``RoomPolish.value``. Recomputes
    prestige_from_dwellings for everyone whose primary home is this room
    (#670 home-anchored rule), plus the building owner when their home is
    in this building.
    """
    from django.db.models import Q  # noqa: PLC0415
    from django.utils import timezone  # noqa: PLC0415

    from world.locations.models import LocationTenancy  # noqa: PLC0415

    rp, _created = RoomPolish.objects.get_or_create(
        room=room,
        category=category,
        defaults={"value": 0},
    )
    new_value = max(0, rp.value + delta)
    if new_value != rp.value:
        rp.value = new_value
        rp.save(update_fields=["value"])

    # Whoever calls this room home.
    now = timezone.now()
    home_holders = (
        LocationTenancy.objects.filter(room_profile=room, is_primary_home=True)
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=now))
        .select_related("tenant_persona")
    )
    recomputed: set[int] = set()
    for tenancy in home_holders:
        if tenancy.tenant_persona is not None:
            recompute_persona_prestige_from_dwellings(tenancy.tenant_persona)
            recomputed.add(tenancy.tenant_persona_id)

    # The building's owner (their home may be elsewhere in this building).
    owner = _resolve_room_building_owner(room)
    if owner is not None and owner.pk not in recomputed:
        recompute_persona_prestige_from_dwellings(owner)

    return new_value


def _primary_home_room(persona):
    """The RoomProfile of the persona's active primary-home tenancy, or None."""
    from django.db.models import Q  # noqa: PLC0415
    from django.utils import timezone  # noqa: PLC0415

    from world.locations.models import LocationTenancy  # noqa: PLC0415

    now = timezone.now()
    tenancy = (
        LocationTenancy.objects.filter(tenant_persona=persona, is_primary_home=True)
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=now))
        .select_related("room_profile")
        .first()
    )
    return tenancy.room_profile if tenancy else None


def recompute_persona_prestige_from_dwellings(persona) -> int:
    """Read the persona's PRIMARY-HOME polish into ``persona.prestige_from_dwellings``.

    Returns the new value. Writes through ``total_prestige`` denorm.

    Primary-home-anchored (#670, ratified — replaces the earlier
    sum-over-portfolio + double-count):
        the home room's polish
      + the building's polish IFF this persona owns that building
        (``Building.owner_persona``, the polish system's owner notion).
    No primary home designated → 0. Prestige rewards a home, not a
    property portfolio.
    """
    home = _primary_home_room(persona)
    total = 0
    if home is not None:
        total += RoomPolish.objects.filter(room=home).aggregate(total=Sum("value"))["total"] or 0
        if home.area_id is not None:
            total += (
                BuildingPolish.objects.filter(
                    building__area_id=home.area_id,
                    building__owner_persona=persona,
                ).aggregate(total=Sum("value"))["total"]
                or 0
            )
            # Throwback-tier style bonus (#1469): the owned home building's
            # architectural style adds base prestige (PLACEHOLDER magnitudes)
            # under the same ownership condition as building polish.
            total += (
                Building.objects.filter(
                    area_id=home.area_id,
                    owner_persona=persona,
                    architectural_style__isnull=False,
                ).aggregate(total=Sum("architectural_style__prestige_bonus"))["total"]
                or 0
            )
    persona.prestige_from_dwellings = total
    persona.total_prestige = (
        persona.prestige_from_dwellings
        + persona.prestige_from_items
        + persona.prestige_from_orgs
        + persona.prestige_from_deeds
        + persona.prestige_from_fashion
    )
    persona.save(update_fields=["prestige_from_dwellings", "total_prestige"])
    return total


def _resolve_room_building_owner(room):
    """Resolve the persona who owns the building this room is inside.

    Rooms link to Areas via ``RoomProfile.area``. A room inside a
    building shares that building's level=BUILDING Area; the building's
    ``owner_persona`` is what we want here.

    Returns the Persona or None when the room is unhoused (no area), not
    inside a building (area is at a higher level), or the building has
    no owner.
    """
    area = room.area
    if area is None:
        return None
    try:
        building = area.building_profile
    except Building.DoesNotExist:
        return None
    return building.owner_persona
