"""Mothballing — long owner inactivity hides a building and freezes it (#1930).

Ghost towns are authored, not accidental: when a building's owner has been
inactive 90+ days (``CharacterSheet.decay_tier`` LONG_INACTIVE or DORMANT),
the weekly sweep *mothballs* the building — every room's
``RoomProfile.is_public`` flips False (prior values snapshotted to
``MothballedRoomState`` for faithful restore) and ``mothballed_at`` is
stamped, which the upkeep sweep reads to skip all accrual. A hidden
building is indistinguishable from an owner's own privacy choice — it
carries no "inactive" label.

On the owner's return the same sweep unmothballs: snapshots restore,
the stamp clears, and the miss counter zeroes (no back-billing — absence
costs opportunity, never principal; arrears accrued *before* the mothball
remain, already capped).

This is its own cron rather than a step inside roster's
``sweep_activity_states``: the dependency must point buildings → roster
(ADR-0010 specific→general), not the reverse.

Vocabulary: **mothballed** (see AGENT_GLOSSARY.md) — deliberately not
"dormant", which collides with ``DecayTier.DORMANT`` (365d inactivity).
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from world.buildings.models import Building, MothballedRoomState

logger = logging.getLogger(__name__)


def _owner_is_long_inactive(building: Building) -> bool:
    """Whether the owner's activity signal warrants mothballing.

    Uses the existing 14/30/90/365d ``decay_tier`` ladder; the mothball
    threshold is LONG_INACTIVE (90d+). Ownerless buildings never mothball
    (staff-authored scenery stays put).
    """
    from world.character_sheets.types import DecayTier  # noqa: PLC0415

    if building.owner_persona is None:
        return False
    tier = building.owner_persona.character_sheet.decay_tier
    return tier in {DecayTier.LONG_INACTIVE, DecayTier.DORMANT}


@transaction.atomic
def mothball_building(building: Building) -> int:
    """Hide ``building`` from the grid and freeze its accrual.

    Snapshots each room's ``is_public`` to ``MothballedRoomState``, flips
    the rooms private, and stamps ``mothballed_at``. Returns the number
    of rooms hidden. No-op (returns 0) when already mothballed.
    """
    if building.mothballed_at is not None:
        return 0

    hidden = 0
    rooms = building.area.rooms.all() if building.area_id is not None else []
    for room_profile in rooms:
        MothballedRoomState.objects.create(
            building=building,
            room_profile=room_profile,
            was_public=room_profile.is_public,
        )
        if room_profile.is_public:
            room_profile.is_public = False
            room_profile.save(update_fields=["is_public"])
            hidden += 1

    building.mothballed_at = timezone.now()
    building.save(update_fields=["mothballed_at"])
    return hidden


@transaction.atomic
def unmothball_building(building: Building) -> int:
    """Restore a mothballed building on the owner's return.

    Restores each snapshotted room's prior ``is_public`` (per-row .save()
    so the identity map stays coherent), deletes the snapshots, clears
    ``mothballed_at``, and zeroes the miss counter — accrual resumes
    fresh, with no back-billing for the mothballed span. Returns the
    number of rooms restored. No-op (returns 0) when not mothballed.
    """
    if building.mothballed_at is None:
        return 0

    restored = 0
    snapshots = MothballedRoomState.objects.filter(building=building).select_related("room_profile")
    for snapshot in snapshots:
        room_profile = snapshot.room_profile
        if room_profile.is_public != snapshot.was_public:
            room_profile.is_public = snapshot.was_public
            room_profile.save(update_fields=["is_public"])
        restored += 1
        snapshot.delete()

    building.mothballed_at = None
    building.consecutive_missed_upkeep = 0
    building.save(update_fields=["mothballed_at", "consecutive_missed_upkeep"])
    return restored


def sweep_building_mothballs() -> dict[str, int]:
    """Weekly: mothball long-inactive owners' buildings; restore returned ones.

    Returns a small telemetry dict so the scheduler can log per-tick volume.
    """
    mothballed = restored = 0
    buildings = Building.objects.exclude(owner_persona=None).select_related(
        "owner_persona__character_sheet", "area"
    )
    for building in buildings.iterator():
        long_inactive = _owner_is_long_inactive(building)
        if building.mothballed_at is None and long_inactive:
            mothball_building(building)
            mothballed += 1
        elif building.mothballed_at is not None and not long_inactive:
            unmothball_building(building)
            restored += 1

    if mothballed or restored:
        logger.info("buildings.mothball_sweep: mothballed=%d restored=%d", mothballed, restored)
    return {"mothballed": mothballed, "restored": restored}
