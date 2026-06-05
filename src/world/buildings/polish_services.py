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
    prestige_from_dwellings for the room's tenant_persona AND rolls up
    to the building owner (intentional double-count per spec).
    """
    rp, _created = RoomPolish.objects.get_or_create(
        room=room,
        category=category,
        defaults={"value": 0},
    )
    new_value = max(0, rp.value + delta)
    if new_value != rp.value:
        rp.value = new_value
        rp.save(update_fields=["value"])

    # Tenant credit.
    if room.tenant_persona_id is not None:
        recompute_persona_prestige_from_dwellings(room.tenant_persona)

    # Roll-up to building owner (when the room is inside a building).
    owner = _resolve_room_building_owner(room)
    tenant_pk = room.tenant_persona.pk if room.tenant_persona_id is not None else None
    if owner is not None and owner.pk != tenant_pk:
        recompute_persona_prestige_from_dwellings(owner)

    return new_value


def recompute_persona_prestige_from_dwellings(persona) -> int:
    """Read building + room polish totals into ``persona.prestige_from_dwellings``.

    Returns the new value. Writes through ``total_prestige`` denorm.

    Persona's total is:
        sum of value over BuildingPolish rows for buildings this persona owns
      + sum of value over RoomPolish rows for rooms this persona tenants
      + (double-count): sum of value over RoomPolish rows for rooms in
        buildings this persona owns (regardless of tenant)
    """
    owned_buildings_polish = (
        BuildingPolish.objects.filter(building__owner_persona=persona).aggregate(
            total=Sum("value")
        )["total"]
        or 0
    )
    tenanted_rooms_polish = (
        RoomPolish.objects.filter(room__tenant_persona=persona).aggregate(total=Sum("value"))[
            "total"
        ]
        or 0
    )
    # Roll-up: every room in any building this persona owns, regardless of
    # whether they're also the tenant. When they ARE the tenant, this adds
    # the room's polish a SECOND time on purpose (the spec's intentional
    # double-count for owner-tenanting).
    owned_building_rooms_polish = (
        RoomPolish.objects.filter(
            room__area__building_profile__owner_persona=persona,
        ).aggregate(total=Sum("value"))["total"]
        or 0
    )

    total = owned_buildings_polish + tenanted_rooms_polish + owned_building_rooms_polish
    if total == persona.prestige_from_dwellings:
        return total
    persona.prestige_from_dwellings = total
    persona.total_prestige = (
        persona.prestige_from_dwellings
        + persona.prestige_from_items
        + persona.prestige_from_orgs
        + persona.prestige_from_deeds
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
