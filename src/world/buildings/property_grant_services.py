"""Generic "grant a persona an already-existing Building" primitive.

Not tied to character creation, player progression, or any specific content —
grant_property_house is callable from anywhere (e.g., during finalization via
a PropertyGrantProfile, a GM/story action, or a later relocation flow). Actual
content that instantiates a PropertyGrantProfile lives in fixtures/content data,
not in this module — see PropertyGrantProfile's docstring.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.buildings.constants import COPPERS_PER_PROGRESS_POINT
from world.buildings.room_services import RoomBuildError

if TYPE_CHECKING:
    from world.areas.models import Area
    from world.buildings.models import Building, PropertyGrantProfile
    from world.projects.models import Project
    from world.scenes.models import Persona

_PLACEHOLDER_WARD_SLUG = "property-grant-placeholder-ward"


def _placeholder_ward_area() -> Area:
    """Get-or-create the shared fallback placeholder Ward Area.

    Slug-keyed (Area.slug is unique) for concurrency-safe idempotency.
    origin is left at its default (PLAYER), so this never exports as
    authored grid content — real content replaces a profile's ward_area
    via fixture upsert with no code change.
    """
    from world.areas.constants import AreaLevel  # noqa: PLC0415
    from world.areas.models import Area  # noqa: PLC0415

    area, _ = Area.objects.get_or_create(
        slug=_PLACEHOLDER_WARD_SLUG,
        defaults={"name": "Unclaimed Properties (placeholder)", "level": AreaLevel.WARD},
    )
    return area


def grant_property_house(persona: Persona, profile: PropertyGrantProfile) -> Building:
    """Grant *persona* ownership of a freshly created Building per *profile*.

    Creates a BUILDING-level Area under the profile's ward (or the shared
    placeholder ward if unset), a Building at ``profile.initial_condition_tier``,
    and one entry room — the same minimal shape ``complete_building_construction``
    produces, minus the permit/project. Stamps ``property_granted_at`` always;
    stamps ``property_activated_at`` immediately too when the profile carries
    no activation arc (``activation_target_tier is None``).
    """
    from world.areas.constants import AreaLevel  # noqa: PLC0415
    from world.areas.models import Area  # noqa: PLC0415
    from world.buildings.models import Building, BuildingSizeTier  # noqa: PLC0415
    from world.buildings.services import create_entry_room  # noqa: PLC0415

    ward = profile.ward_area or _placeholder_ward_area()
    now = timezone.now()
    with transaction.atomic():
        area = Area.objects.create(
            name=f"{profile.name} grant for {persona}",
            level=AreaLevel.BUILDING,
            parent=ward,
        )
        building = Building.objects.create(
            area=area,
            kind=profile.building_kind,
            condition_tier=profile.initial_condition_tier,
            target_size=1,
            target_grandeur=1,
            space_budget=BuildingSizeTier.objects.get(tier=1).space_budget,
            owner_persona=persona,
            granted_via_profile=profile,
            property_granted_at=now,
            property_activated_at=(now if profile.activation_target_tier is None else None),
        )
        room = create_entry_room(building, "Entry Hall")
        building.entry_room = room
        building.save(update_fields=["entry_room"])
    return building


def _open_activation_project(building: Building) -> Project | None:
    """The building's not-yet-resolved BUILDING_ACTIVATION Project, if one exists."""
    from world.buildings.models import BuildingActivationDetails  # noqa: PLC0415
    from world.projects.constants import ProjectStatus  # noqa: PLC0415

    details = (
        BuildingActivationDetails.objects.filter(
            building=building,
            project__status__in=(
                ProjectStatus.PLANNING,
                ProjectStatus.ACTIVE,
                ProjectStatus.RESOLVING,
            ),
        )
        .select_related("project")
        .first()
    )
    return details.project if details is not None else None


def start_building_activation(*, persona: Persona, building: Building) -> Project:
    """Open a BUILDING_ACTIVATION project bringing *building* to its profile's target tier.

    Owner-gated. Refuses when the building was never granted, is already
    activated, its grant profile has no activation arc configured, or it
    already has an open activation project.
    """
    from world.buildings.models import BuildingActivationDetails  # noqa: PLC0415
    from world.locations.services import is_owner  # noqa: PLC0415
    from world.projects.constants import CompletionMode, ProjectKind, ProjectStatus  # noqa: PLC0415
    from world.projects.models import Project  # noqa: PLC0415

    entry = building.entry_room
    if entry is None or not is_owner(persona, entry.objectdb):
        msg = "Only the building's owner can commission its activation."
        raise RoomBuildError(msg)
    if building.property_granted_at is None:
        msg = "This building wasn't a property grant — there's nothing to activate."
        raise RoomBuildError(msg)
    if building.property_activated_at is not None:
        msg = "This house has already been brought to life."
        raise RoomBuildError(msg)
    profile = building.granted_via_profile
    if profile is None or profile.activation_target_tier is None:
        msg = "This property doesn't need activation."
        raise RoomBuildError(msg)
    if _open_activation_project(building) is not None:
        msg = "An activation project is already underway."
        raise RoomBuildError(msg)

    cost = profile.activation_cost_floor_coppers * building.target_size
    threshold = max(1, cost // COPPERS_PER_PROGRESS_POINT)
    now = timezone.now()
    with transaction.atomic():
        project = Project.objects.create(
            kind=ProjectKind.BUILDING_ACTIVATION,
            completion_mode=CompletionMode.SINGLE_THRESHOLD,
            status=ProjectStatus.ACTIVE,
            owner_persona=persona,
            started_at=now,
            time_limit=now + timedelta(days=30),
            threshold_target=threshold,
            description=f"Bring {building} to life",
        )
        BuildingActivationDetails.objects.create(
            project=project,
            building=building,
            target_tier=profile.activation_target_tier,
        )
    return project


def complete_building_activation(project, outcome_tier: object | None = None) -> None:  # noqa: ARG001
    """Kind handler: set the building's condition_tier to the snapshotted target, exactly once.

    Registered with register_kind_handler at app-ready time; signature matches
    the framework's KindHandler (project, outcome_tier). Idempotent via the
    applied_at claim-filter, mirroring complete_building_renovation.
    """
    from world.buildings.models import BuildingActivationDetails  # noqa: PLC0415
    from world.buildings.upkeep_services import set_condition_tier  # noqa: PLC0415

    with transaction.atomic():
        claimed = BuildingActivationDetails.objects.filter(
            project=project, applied_at__isnull=True
        ).update(applied_at=timezone.now())
        if not claimed:
            return
        details = BuildingActivationDetails.objects.get(project=project)
        building = details.building
        set_condition_tier(building, details.target_tier)
        building.property_activated_at = timezone.now()
        building.save(update_fields=["property_activated_at"])
