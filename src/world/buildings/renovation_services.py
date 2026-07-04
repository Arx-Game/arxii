"""``BUILDING_RENOVATION`` project kind: re-point a Building to a new catalog kind.

A renovation is a funded ``SINGLE_THRESHOLD`` Project that, on completion,
re-points an existing ``Building`` to a different admin-authored
``BuildingKind`` — changing the building's descriptive flag set (e.g. a
residential manor becomes an "Occult Manor" after building an underground
lair complex). It does not change ``target_size`` / ``space_budget`` (use
``BUILDING_EXTENSION`` / ``BUILDING_UPGRADE`` for those).

Set-once semantics on completion (mirrors ``FortificationUpgradeDetails``):
the handler assigns ``Building.kind`` to the target exactly once via the
``applied_at`` idempotency marker. Unlike fortification there is no ordering
guard — a catalog-kind label has no numeric ladder, so a later renovation may
re-point to any target kind, including back to the original.

See ``world/buildings/AGENT_GLOSSARY.md``: the nine boolean flags are
catalog-level cosmetic/filter tags on ``BuildingKind``, not per-instance
state, so a renovation swaps the catalog row rather than mutating flags on
``Building`` itself.
"""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.buildings.room_constants import RENOVATION_THRESHOLD
from world.buildings.room_services import RoomBuildError

if TYPE_CHECKING:
    from world.buildings.models import Building, BuildingKind
    from world.projects.models import Project
    from world.scenes.models import Persona

logger = logging.getLogger(__name__)


def start_building_renovation(
    *, persona: Persona, building: Building, target_kind: BuildingKind
) -> Project:
    """Open a ``BUILDING_RENOVATION`` project re-pointing *building* to *target_kind*.

    Owner-gated. Threshold is the flat ``RENOVATION_THRESHOLD`` (PLACEHOLDER
    pending the economy pass); funding flows through the standard contribution
    pipe. Refuses a no-op renovation (target is the building's current kind).

    Args:
        persona: The funding persona (project owner). Must own the building.
        building: The Building being re-classified.
        target_kind: The admin-authored ``BuildingKind`` to re-point to on
            completion. Must differ from the building's current kind.

    Returns:
        The newly created Project.

    Raises:
        RoomBuildError: If *persona* does not own the building, or *target_kind*
            is already the building's current kind.
    """
    from world.buildings.models import BuildingRenovationDetails  # noqa: PLC0415
    from world.locations.services import is_owner  # noqa: PLC0415
    from world.projects.constants import CompletionMode, ProjectKind  # noqa: PLC0415
    from world.projects.models import Project  # noqa: PLC0415

    entry = building.entry_room
    if entry is None or not is_owner(persona, entry.objectdb):
        msg = "Only the building's owner can commission a renovation."
        raise RoomBuildError(msg)
    if target_kind == building.kind:
        msg = "The building is already of that kind."
        raise RoomBuildError(msg)

    now = timezone.now()
    with transaction.atomic():
        project = Project.objects.create(
            kind=ProjectKind.BUILDING_RENOVATION,
            completion_mode=CompletionMode.SINGLE_THRESHOLD,
            owner_persona=persona,
            started_at=now,
            time_limit=now + timedelta(days=30),
            threshold_target=RENOVATION_THRESHOLD,
            description=f"Renovate {building} into {target_kind}",
        )
        BuildingRenovationDetails.objects.create(
            project=project,
            building=building,
            target_kind=target_kind,
        )
    return project


def complete_building_renovation(project, outcome_tier: object | None = None) -> None:  # noqa: ARG001
    """Kind handler: re-point the building's ``kind`` to the target, exactly once.

    Registered with ``register_kind_handler`` at app-ready time; signature
    matches the framework's ``KindHandler`` (project, outcome_tier).
    Idempotent via the ``applied_at`` claim-filter — a second call sees the
    non-null marker and no-ops even though a cached instance is stale.

    Instance mutation, not queryset ``.update()``: ``SharedMemoryModel`` keeps
    one live instance per row, and a queryset update would leave every holder
    of it (including this test run) reading the old ``kind``.
    """
    from world.buildings.models import BuildingRenovationDetails  # noqa: PLC0415

    with transaction.atomic():
        # The claim filter hits the DB, so a second call sees the non-null
        # applied_at and no-ops even though the cached instance is stale.
        claimed = BuildingRenovationDetails.objects.filter(
            project=project, applied_at__isnull=True
        ).update(applied_at=timezone.now())
        if not claimed:
            return
        details = BuildingRenovationDetails.objects.get(project=project)
        # Instance mutation, not queryset .update(): SharedMemoryModel keeps
        # one live instance per row, and a queryset update would leave every
        # holder of it (including this test run) reading the old kind.
        building = details.building
        building.kind = details.target_kind
        building.save(update_fields=["kind"])

    logger.info(
        "building renovation %s applied: building %s re-pointed to kind %s.",
        project.pk,
        details.building_id,
        details.target_kind_id,
    )
