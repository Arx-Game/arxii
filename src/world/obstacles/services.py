"""Service functions for the obstacle and bypass system."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.obstacles.constants import DiscoveryType
from world.obstacles.models import (
    BypassCheckRequirement,
    BypassOption,
    CharacterBypassDiscovery,
    ObstacleInstance,
)
from world.obstacles.types import BypassAvailability

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


def get_bypass_options_for_character(
    obstacle_instance: ObstacleInstance,
    character: ObjectDB,
    character_capabilities: dict[str, int],
) -> list[BypassAvailability]:
    """
    Return available bypass options for a character facing an obstacle.

    Filters by discovery (obvious + discovered). For each visible option,
    checks capability requirements against the provided capability values.
    Includes check requirement info with difficulty scaled by obstacle severity.
    """
    template = obstacle_instance.template
    severity = template.severity

    # Get all bypass options from the obstacle's properties
    property_ids = template.properties.values_list("id", flat=True)
    bypass_options = (
        BypassOption.objects.filter(obstacle_property_id__in=property_ids)
        .prefetch_related("capability_requirements__capability_type")
        .select_related("check_requirement__check_type")
    )

    # Get character's discovered bypass option IDs
    discovered_ids = set(
        CharacterBypassDiscovery.objects.filter(
            character=character,
        ).values_list("bypass_option_id", flat=True)
    )

    results: list[BypassAvailability] = []
    for bypass in bypass_options:
        # Filter by discovery type
        if bypass.discovery_type == DiscoveryType.DISCOVERABLE:
            if bypass.pk not in discovered_ids:
                continue

        # Check capability requirements
        missing: list[str] = []
        for req in bypass.capability_requirements.all():
            cap_name = req.capability_type.name
            char_value = character_capabilities.get(cap_name, 0)
            if char_value < req.minimum_value:
                missing.append(cap_name)

        # Get check requirement info
        check_type = None
        effective_difficulty = 0
        try:
            check_req = bypass.check_requirement
            check_type = check_req.check_type
            effective_difficulty = check_req.base_target_difficulty * severity
        except BypassCheckRequirement.DoesNotExist:
            pass

        results.append(
            BypassAvailability(
                bypass_option=bypass,
                can_attempt=len(missing) == 0,
                missing_capabilities=missing,
                check_type=check_type,
                effective_difficulty=effective_difficulty,
            )
        )

    return results
