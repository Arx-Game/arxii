"""Lab station service layer (#1234) — the LAB RoomFeatureServiceStrategy handler
and the coppers-only durability repair economy.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils import timezone

from world.items.crafting.constants import LAB_BASE_DURABILITY_PER_LEVEL
from world.items.crafting.models import LabStationDetails

if TYPE_CHECKING:
    from world.checks.types import CheckOutcome
    from world.projects.models import Project


def _max_durability_for_level(level: int) -> int:
    return LAB_BASE_DURABILITY_PER_LEVEL * level


def handle_lab_progression(
    project: Project,
    target_level: int,
    outcome_tier: CheckOutcome | None = None,  # noqa: ARG001
) -> None:
    """LAB strategy (#1234): install or level the feature instance + its station.

    Mirrors ``handle_command_center_progression`` — a plain-project-installed kind,
    level 1 creates the instance, higher targets bump it. On both install AND
    upgrade, the station's durability is (re)set to the new level's max — an
    upgrade project is a refurbishment, not just a bigger cap on old wear.
    """
    from world.room_features.models import (  # noqa: PLC0415
        RoomFeatureInstance,
        RoomFeatureProgressionDetails,
    )

    details = RoomFeatureProgressionDetails.objects.select_related(
        "target_room_profile", "target_feature_kind"
    ).get(project=project)
    instance = (
        RoomFeatureInstance.objects.filter(
            room_profile=details.target_room_profile,
            feature_kind=details.target_feature_kind,
        )
        .active()
        .first()
    )
    new_max = _max_durability_for_level(target_level)

    if instance is None:
        instance = RoomFeatureInstance.objects.create(
            room_profile=details.target_room_profile,
            feature_kind=details.target_feature_kind,
            level=max(1, target_level),
        )
        LabStationDetails.objects.create(
            feature_instance=instance, durability=new_max, max_durability=new_max
        )
        return

    if target_level > instance.level:
        instance.level = target_level
        instance.last_upgraded_at = timezone.now()
        instance.save(update_fields=["level", "last_upgraded_at"])
        station, _ = LabStationDetails.objects.get_or_create(
            feature_instance=instance,
            defaults={"durability": new_max, "max_durability": new_max},
        )
        station.max_durability = new_max
        station.durability = new_max
        station.save(update_fields=["max_durability", "durability"])
