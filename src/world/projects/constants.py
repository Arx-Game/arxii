"""TextChoices enums for the projects framework."""

from django.db import models


class ProjectKind(models.TextChoices):
    """Discriminator for per-kind details models.

    Each kind maps to a per-kind details model (e.g., BuildingConstructionDetails
    for BUILDING_CONSTRUCTION) and a service handler registered via
    register_kind_handler. TEST_KIND is used only in Phase D's framework tests.
    """

    BUILDING_CONSTRUCTION = "BUILDING_CONSTRUCTION", "Building Construction"
    ROOM_FEATURE_PROGRESSION = "ROOM_FEATURE_PROGRESSION", "Room Feature Progression"
    TEST_KIND = "TEST_KIND", "Test Kind (framework tests only)"


class ProjectStatus(models.TextChoices):
    """Lifecycle states a Project transitions through."""

    PLANNING = "PLANNING", "Planning"
    ACTIVE = "ACTIVE", "Active"
    RESOLVING = "RESOLVING", "Resolving"
    COMPLETED = "COMPLETED", "Completed"
    FAILED = "FAILED", "Failed"
    CANCELLED = "CANCELLED", "Cancelled"


class CompletionMode(models.TextChoices):
    """How a Project decides when to resolve.

    SINGLE_THRESHOLD: completes on (progress >= threshold) OR (now >= time_limit).
    TIERED_PERIOD:    completes only when now >= time_limit; tier determined by
                      which per-kind tier_thresholds were crossed.
    """

    SINGLE_THRESHOLD = "SINGLE_THRESHOLD", "Single Threshold"
    TIERED_PERIOD = "TIERED_PERIOD", "Tiered Period"


class ContributionKind(models.TextChoices):
    """Discriminator for Contribution rows.

    Exactly one kind-specific column is populated per row.
    """

    AP = "AP", "Action Points"
    MONEY = "MONEY", "Money"
    ITEM = "ITEM", "Item"
    CHECK = "CHECK", "Skill Check"


class ContributionPrivacy(models.TextChoices):
    """Whether a contribution's intent text is visible to others."""

    PRIVATE = "PRIVATE", "Private (actor only)"
    GROUP = "GROUP", "Group (all project contributors)"
