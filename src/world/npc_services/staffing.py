"""Venue auto-staffing (#2827 phase 1).

A `StaffingProfile` keyed to a `BuildingKind` describes the baseline crew a
venue of that kind keeps. It applies automatically when the building
activates (generalizing the Town Crier feature-placement pattern) and is
re-ensured by a weekly refill sweep, so an extracted worker's slot
eventually refills with a fresh faceless hire.

Slot semantics: a profile line is a (role, room) slot, backed by the
Functionary unique constraint. Refilling a vacated slot RESETS it — active,
no name override, no persona link — a new nobody takes the job; the
previous holder's identity (sheet/persona/asset rows) is untouched. Staff
curation happens at the profile level: prune the line, not the placement,
or the sweep will re-staff it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from world.npc_services.functionaries import place_functionary
from world.npc_services.models import Functionary, StaffingProfile

if TYPE_CHECKING:
    from world.buildings.models import Building


def _profile_for(building: Building) -> StaffingProfile | None:
    if building.kind_id is None:
        return None
    return StaffingProfile.objects.filter(building_kind_id=building.kind_id).first()


@transaction.atomic
def ensure_staffing_for_building(building: Building) -> int:
    """Ensure the building's entry room carries its kind's baseline crew.

    Idempotent: existing active slots are untouched; vacated (inactive)
    slots reset to a fresh faceless worker; missing slots are placed.
    Returns the number of slots created or refilled.
    """
    profile = _profile_for(building)
    if profile is None or building.entry_room_id is None:
        return 0
    room = building.entry_room
    changed = 0
    for line in profile.lines.select_related("role"):
        existing = Functionary.objects.filter(role=line.role, room=room).first()
        if existing is None:
            place_functionary(role=line.role, room=room)
            changed += 1
        elif not existing.is_active:
            existing.is_active = True
            existing.name_override = ""
            existing.description_override = ""
            existing.persona = None
            existing.save(
                update_fields=["is_active", "name_override", "description_override", "persona"]
            )
            changed += 1
    return changed


def refill_staffing_sweep() -> int:
    """Weekly cron: re-ensure staffing for every activated, profiled building."""
    from world.buildings.models import Building  # noqa: PLC0415

    profiled_kind_ids = StaffingProfile.objects.values_list("building_kind_id", flat=True)
    buildings = Building.objects.filter(
        kind_id__in=profiled_kind_ids,
        property_activated_at__isnull=False,
        entry_room__isnull=False,
    ).select_related("entry_room", "kind")
    total = 0
    for building in buildings:
        total += ensure_staffing_for_building(building)
    return total
