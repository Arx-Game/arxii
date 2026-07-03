"""Persistent fortification-investment services (#1713).

A stronghold's defenses are a player-built investment, not authored fresh per
battle: covenants fund a FORTIFICATION_UPGRADE Project through the ordinary
Project/Contribution pipe (money/AP/item/check), and completing it raises
Building.fortification_level. A battle's Fortification.max_integrity is then
snapshotted from that level once, at battle-creation time (see
world.battles.services.create_fortification) — this module never touches
battles models directly.

Monotonic max-set on completion (not additive, unlike BuildingExtensionDetails):
target_level is the natural authoring unit for a level (not a delta), and a naive
overwrite could regress fortification_level if a lower-target Project happens to
complete after a higher-target one already has. max(current, target_level)
makes completion order irrelevant.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.buildings.room_constants import (
    FORTIFICATION_UPGRADE_THRESHOLD_PER_LEVEL,
    MAX_FORTIFICATION_LEVEL,
)

if TYPE_CHECKING:
    from world.buildings.models import Building
    from world.projects.models import Project
    from world.scenes.models import Persona


class FortificationLevelExceedsMaximumError(ValueError):
    """Raised when a FORTIFICATION_UPGRADE target_level exceeds MAX_FORTIFICATION_LEVEL,
    or doesn't exceed the building's current level (#1713). Subclasses ValueError,
    mirroring buildings.services.PermitValidationError's ValueError-subclass shape."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


def start_fortification_upgrade(
    *, persona: Persona, building: Building, target_level: int
) -> Project:
    """Open a FORTIFICATION_UPGRADE project raising *building* to *target_level*.

    Args:
        persona: The funding persona (project owner).
        building: The Building whose fortification_level this upgrades.
        target_level: The level this upgrade targets on completion. Must be
            greater than the building's current level and at most
            MAX_FORTIFICATION_LEVEL.

    Raises:
        FortificationLevelExceedsMaximumError: If target_level is not greater
            than the building's current fortification_level, or exceeds
            MAX_FORTIFICATION_LEVEL.

    Returns:
        The newly created Project.
    """
    from world.buildings.models import FortificationUpgradeDetails  # noqa: PLC0415
    from world.projects.constants import CompletionMode, ProjectKind  # noqa: PLC0415
    from world.projects.models import Project  # noqa: PLC0415

    if target_level > MAX_FORTIFICATION_LEVEL:
        msg = f"Fortification level cannot exceed {MAX_FORTIFICATION_LEVEL}."
        raise FortificationLevelExceedsMaximumError(msg)
    if target_level <= building.fortification_level:
        msg = "target_level must exceed the building's current fortification_level."
        raise FortificationLevelExceedsMaximumError(msg)

    now = timezone.now()
    with transaction.atomic():
        project = Project.objects.create(
            kind=ProjectKind.FORTIFICATION_UPGRADE,
            completion_mode=CompletionMode.SINGLE_THRESHOLD,
            owner_persona=persona,
            started_at=now,
            time_limit=now + timedelta(days=30),
            threshold_target=target_level * FORTIFICATION_UPGRADE_THRESHOLD_PER_LEVEL,
            description=f"Raise {building}'s fortification level to {target_level}",
        )
        FortificationUpgradeDetails.objects.create(
            project=project,
            building=building,
            target_level=target_level,
        )
    return project


def complete_fortification_upgrade(project, outcome_tier: object | None = None) -> None:  # noqa: ARG001
    """Kind handler: raise the building's fortification_level, exactly once, never
    downward (#1713).

    Registered with register_kind_handler at app-ready time; signature matches
    the framework's KindHandler (project, outcome_tier).
    """
    from world.buildings.models import FortificationUpgradeDetails  # noqa: PLC0415

    with transaction.atomic():
        # The claim filter hits the DB, so a second call sees the non-null
        # applied_at and no-ops even though the cached instance is stale.
        claimed = FortificationUpgradeDetails.objects.filter(
            project=project, applied_at__isnull=True
        ).update(applied_at=timezone.now())
        if not claimed:
            return
        details = FortificationUpgradeDetails.objects.get(project=project)
        # Instance mutation, not queryset .update(): SharedMemoryModel keeps one
        # live instance per row; monotonic max-set so a lower-target Project
        # completing after a higher one already applied never regresses the level.
        building = details.building
        building.fortification_level = max(building.fortification_level, details.target_level)
        building.save(update_fields=["fortification_level"])
