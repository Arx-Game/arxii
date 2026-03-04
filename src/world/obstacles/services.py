"""Service functions for the obstacle and bypass system."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.checks.services import perform_check
from world.obstacles.constants import DiscoveryType, ResolutionType
from world.obstacles.models import (
    BypassCheckRequirement,
    BypassOption,
    CharacterBypassDiscovery,
    CharacterBypassRecord,
    ObstacleInstance,
)
from world.obstacles.types import BypassAttemptResult, BypassAvailability

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


def attempt_bypass(
    obstacle_instance: ObstacleInstance,
    bypass_option: BypassOption,
    character: ObjectDB,
    character_capabilities: dict[str, int],
) -> BypassAttemptResult:
    """
    Attempt to bypass an obstacle using a specific bypass option.

    Verifies capability requirements, runs check if needed, and resolves
    the obstacle based on the bypass option's resolution type.
    """
    # Verify capability requirements
    for req in bypass_option.capability_requirements.select_related("capability_type"):
        cap_name = req.capability_type.name
        char_value = character_capabilities.get(cap_name, 0)
        if char_value < req.minimum_value:
            return BypassAttemptResult(
                success=False,
                message=f"Requires {cap_name} >= {req.minimum_value}.",
            )

    # Run check if required
    check_result = None
    try:
        check_req = bypass_option.check_requirement
        severity = obstacle_instance.template.severity
        effective_difficulty = check_req.base_target_difficulty * severity
        check_result = perform_check(
            character,
            check_req.check_type,
            target_difficulty=effective_difficulty,
        )
        if check_result.success_level < 0:
            return BypassAttemptResult(
                success=False,
                message="Check failed.",
                check_result=check_result,
            )
    except BypassCheckRequirement.DoesNotExist:
        pass

    # Resolve based on resolution type
    resolution_type = bypass_option.resolution_type
    obstacle_destroyed = False
    obstacle_suppressed_rounds = 0

    if resolution_type == ResolutionType.DESTROY:
        obstacle_instance.is_active = False
        obstacle_instance.save(update_fields=["is_active"])
        obstacle_destroyed = True
    elif resolution_type == ResolutionType.PERSONAL:
        CharacterBypassRecord.objects.create(
            character=character,
            obstacle_instance=obstacle_instance,
            bypass_option=bypass_option,
        )
    elif resolution_type == ResolutionType.TEMPORARY:
        obstacle_suppressed_rounds = bypass_option.resolution_duration_rounds or 0
        obstacle_instance.is_active = False
        obstacle_instance.save(update_fields=["is_active"])

    return BypassAttemptResult(
        success=True,
        check_result=check_result,
        obstacle_destroyed=obstacle_destroyed,
        obstacle_suppressed_rounds=obstacle_suppressed_rounds,
    )
