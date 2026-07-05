"""``BUILDING_UPGRADE`` project kind: bump a Building's size tier.

A size upgrade is a funded ``SINGLE_THRESHOLD`` Project that, on completion,
raises an existing ``Building``'s ``target_size`` to a higher tier and
re-snapshots ``space_budget`` from the ``BuildingSizeTier`` table — e.g.
upgrading a tier-3 House (250 units) to a tier-4 Manor (600 units). It does
not change the building's ``kind`` (use ``BUILDING_RENOVATION`` for that).

Monotonic max-set on completion (mirrors ``FortificationUpgradeDetails``):
the handler sets ``building.target_size = max(current, new_target_size)`` so
a lower-target upgrade completing after a higher one doesn't regress the
size. ``space_budget`` is re-snapshotted from the new ``target_size`` — but
only if the size actually increased, so a no-op max-set doesn't clobber a
prior higher upgrade's budget.
"""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.buildings.room_constants import (
    MAX_BUILDING_SIZE_TIER,
    UPGRADE_THRESHOLD_PER_TIER,
)
from world.buildings.room_services import RoomBuildError

if TYPE_CHECKING:
    from world.buildings.models import Building
    from world.projects.models import Project
    from world.scenes.models import Persona

logger = logging.getLogger(__name__)


class BuildingUpgradeError(ValueError):
    """Raised when a BUILDING_UPGRADE new_target_size is invalid.

    Subclasses ValueError, mirroring FortificationLevelExceedsMaximumError's
    ValueError-subclass shape.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)


def start_building_upgrade(
    *, persona: Persona, building: Building, new_target_size: int
) -> Project:
    """Open a ``BUILDING_UPGRADE`` project raising *building* to *new_target_size*.

    Owner-gated. Threshold scales per-tier (``UPGRADE_THRESHOLD_PER_TIER ×
    new_target_size``); funding flows through the standard contribution pipe.
    Refuses a no-op upgrade (target is the building's current size) and an
    over-cap target (exceeds ``MAX_BUILDING_SIZE_TIER``).

    Args:
        persona: The funding persona (project owner). Must own the building.
        building: The Building being upgraded.
        new_target_size: The size tier this upgrade targets on completion.
            Must be greater than the building's current ``target_size`` and
            at most ``MAX_BUILDING_SIZE_TIER``.

    Returns:
        The newly created Project.

    Raises:
        BuildingUpgradeError: If *new_target_size* exceeds
            ``MAX_BUILDING_SIZE_TIER`` or doesn't exceed the building's
            current ``target_size``.
        RoomBuildError: If *persona* does not own the building.
    """
    from world.buildings.models import BuildingUpgradeDetails  # noqa: PLC0415
    from world.locations.services import is_owner  # noqa: PLC0415
    from world.projects.constants import CompletionMode, ProjectKind  # noqa: PLC0415
    from world.projects.models import Project  # noqa: PLC0415

    if new_target_size > MAX_BUILDING_SIZE_TIER:
        msg = f"Building size tier cannot exceed {MAX_BUILDING_SIZE_TIER}."
        raise BuildingUpgradeError(msg)
    if new_target_size <= building.target_size:
        msg = "new_target_size must exceed the building's current target_size."
        raise BuildingUpgradeError(msg)

    entry = building.entry_room
    if entry is None or not is_owner(persona, entry.objectdb):
        msg = "Only the building's owner can commission an upgrade."
        raise RoomBuildError(msg)

    now = timezone.now()
    with transaction.atomic():
        project = Project.objects.create(
            kind=ProjectKind.BUILDING_UPGRADE,
            completion_mode=CompletionMode.SINGLE_THRESHOLD,
            owner_persona=persona,
            started_at=now,
            time_limit=now + timedelta(days=30),
            threshold_target=new_target_size * UPGRADE_THRESHOLD_PER_TIER,
            description=f"Upgrade {building} to size tier {new_target_size}",
        )
        BuildingUpgradeDetails.objects.create(
            project=project,
            building=building,
            new_target_size=new_target_size,
        )
    return project


def complete_building_upgrade(project, outcome_tier: object | None = None) -> None:  # noqa: ARG001
    """Kind handler: raise the building's ``target_size``, exactly once, never
    downward (#1888).

    Registered with ``register_kind_handler`` at app-ready time; signature
    matches the framework's ``KindHandler`` (project, outcome_tier).
    Idempotent via the ``applied_at`` claim-filter — a second call sees the
    non-null marker and no-ops even though a cached instance is stale.

    Monotonic max-set (mirrors ``complete_fortification_upgrade``):
    ``building.target_size = max(current, new_target_size)``. When the size
    actually increases, ``space_budget`` is re-snapshotted from
    ``BuildingSizeTier[new_target_size]``. A no-op max-set (target ≤ current)
    leaves ``space_budget`` untouched so a late-completing lower-target
    upgrade can't clobber a prior higher upgrade's budget.

    Instance mutation, not queryset ``.update()``: ``SharedMemoryModel`` keeps
    one live instance per row, and a queryset update would leave every holder
    of it (including this test run) reading the old values.
    """
    from world.buildings.models import BuildingSizeTier, BuildingUpgradeDetails  # noqa: PLC0415

    with transaction.atomic():
        # The claim filter hits the DB, so a second call sees the non-null
        # applied_at and no-ops even though the cached instance is stale.
        claimed = BuildingUpgradeDetails.objects.filter(
            project=project, applied_at__isnull=True
        ).update(applied_at=timezone.now())
        if not claimed:
            return
        details = BuildingUpgradeDetails.objects.get(project=project)
        # Instance mutation, not queryset .update(): SharedMemoryModel keeps
        # one live instance per row; monotonic max-set so a lower-target
        # Project completing after a higher one already applied never
        # regresses the size.
        building = details.building
        new_size = max(building.target_size, details.new_target_size)
        if new_size != building.target_size:
            building.target_size = new_size
            building.space_budget = BuildingSizeTier.objects.get(tier=new_size).space_budget
            building.save(update_fields=["target_size", "space_budget"])

    logger.info(
        "building upgrade %s applied: building %s raised to size tier %s.",
        project.pk,
        details.building_id,
        details.new_target_size,
    )
