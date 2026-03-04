"""Models for the obstacle and bypass system."""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.checks.models import CheckType
from world.conditions.models import CapabilityType
from world.obstacles.constants import DiscoveryType, ResolutionType


class ObstacleProperty(SharedMemoryModel):
    """
    Tags describing obstacle characteristics.

    Bypass options attach to properties, ensuring consistency across all
    obstacles sharing a property. Example properties: solid, tall, ice,
    magical, organic, liquid, abyssal.
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    def __str__(self) -> str:
        return self.name


class BypassOption(SharedMemoryModel):
    """
    A way to overcome obstacles with a given property.

    Attached to properties, not individual obstacles. Every obstacle with
    the 'tall' property automatically inherits all 'tall' bypass options
    (e.g., Fly Over, Climb Over). This ensures consistency: if you can
    fly over one tall obstacle, you can fly over all of them.
    """

    obstacle_property = models.ForeignKey(
        ObstacleProperty,
        on_delete=models.CASCADE,
        related_name="bypass_options",
    )
    name = models.CharField(max_length=100)
    description_template = models.TextField(
        blank=True,
        help_text="Narrative text with {variables} for context customization.",
    )
    discovery_type = models.CharField(
        max_length=20,
        choices=DiscoveryType.choices,
        default=DiscoveryType.OBVIOUS,
    )
    resolution_type = models.CharField(
        max_length=20,
        choices=ResolutionType.choices,
        default=ResolutionType.PERSONAL,
    )
    resolution_duration_rounds = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="For TEMPORARY resolution: rounds before obstacle reactivates.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["obstacle_property", "name"],
                name="bypass_option_unique_per_property",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.obstacle_property.name})"


class BypassCapabilityRequirement(SharedMemoryModel):
    """
    Capability threshold to attempt a bypass option.

    Multiple requirements on one bypass option means ALL must be met (AND).
    Nothing is binary: minimum_value is always a threshold comparison, not
    a boolean gate. Even 'impossible' things just require very high values.
    """

    bypass_option = models.ForeignKey(
        BypassOption,
        on_delete=models.CASCADE,
        related_name="capability_requirements",
    )
    capability_type = models.ForeignKey(
        CapabilityType,
        on_delete=models.CASCADE,
    )
    minimum_value = models.PositiveIntegerField(
        default=1,
        help_text="Minimum capability value to attempt this bypass.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["bypass_option", "capability_type"],
                name="bypass_cap_req_unique_per_option",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.bypass_option.name} requires "
            f"{self.capability_type.name} >= {self.minimum_value}"
        )


class BypassCheckRequirement(SharedMemoryModel):
    """
    Check to perform when attempting a bypass.

    Uses the existing check system: perform_check(character, check_type,
    target_difficulty). The effective difficulty is scaled by the obstacle
    template's severity: effective = base_target_difficulty * severity.
    """

    bypass_option = models.OneToOneField(
        BypassOption,
        on_delete=models.CASCADE,
        related_name="check_requirement",
    )
    check_type = models.ForeignKey(
        CheckType,
        on_delete=models.CASCADE,
    )
    base_target_difficulty = models.PositiveIntegerField(
        help_text="Base difficulty in points, scaled by obstacle severity.",
    )

    def __str__(self) -> str:
        return f"{self.bypass_option.name}: {self.check_type.name} vs {self.base_target_difficulty}"
