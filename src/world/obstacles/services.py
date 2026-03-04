"""Service functions for the obstacle and bypass system."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.obstacles.models import ObstacleInstance

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


def get_obstacles_for_object(
    target: ObjectDB,
    character: ObjectDB | None = None,
) -> list[ObstacleInstance]:
    """
    Return active obstacle instances on a game object.

    If character is provided, excludes obstacles that character has
    personally bypassed (PERSONAL resolution records).
    """
    qs = ObstacleInstance.objects.filter(
        target=target,
        is_active=True,
    ).select_related("template")

    if character is not None:
        qs = qs.exclude(bypass_records__character=character)

    return list(qs)
