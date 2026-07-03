"""Lab station service layer (#1234) — the LAB RoomFeatureServiceStrategy handler
and the coppers-only durability repair economy.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils import timezone

from world.items.crafting.constants import (
    LAB_BASE_DURABILITY_PER_LEVEL,
    LAB_REPAIR_COPPER_PER_POINT_PER_LEVEL,
)
from world.items.crafting.models import LabStationDetails

if TYPE_CHECKING:
    from world.checks.types import CheckOutcome
    from world.currency.models import CharacterPurse
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


def repair_station_durability(
    *, station: LabStationDetails, restore_points: int, payer_purse: CharacterPurse
) -> LabStationDetails:
    """Restore up to ``restore_points`` of durability for coppers (#1234).

    Clamps the restored amount to the station's actual deficit, charges
    ``LAB_REPAIR_COPPER_PER_POINT_PER_LEVEL * level * points_restored`` coppers
    via ``currency.services.transfer`` (sink — no destination, money leaves the
    economy per #923). Raises ``django.core.exceptions.ValidationError`` (from
    ``transfer``) on insufficient funds; durability is unchanged in that case
    since the charge happens before the durability write.
    """
    from world.currency.services import transfer  # noqa: PLC0415

    deficit = station.max_durability - station.durability
    points = min(restore_points, deficit)
    if points <= 0:
        return station

    level = station.feature_instance.level
    cost = LAB_REPAIR_COPPER_PER_POINT_PER_LEVEL * level * points
    transfer(amount=cost, reason="Lab station repair", from_purse=payer_purse, to_purse=None)

    station.durability += points
    station.save(update_fields=["durability"])
    return station
