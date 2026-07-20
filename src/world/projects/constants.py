"""TextChoices enums for the projects framework."""

from django.db import models


class ProjectKind(models.TextChoices):
    """Discriminator for per-kind details models.

    Each kind maps to a per-kind details model (e.g., BuildingConstructionDetails
    for BUILDING_CONSTRUCTION) and a service handler registered via
    register_kind_handler. TEST_KIND is used only in Phase D's framework tests.

    RANSOM is special: it has no per-kind details model (the ``Captivity`` that
    points at the project via ``ransom_project`` *is* its details) and it
    completes the instant its threshold is funded rather than on a cron tick —
    see ``register_instant_completion_kind`` (#1500).
    """

    BUILDING_CONSTRUCTION = "BUILDING_CONSTRUCTION", "Building Construction"
    BUILDING_EXTENSION = "BUILDING_EXTENSION", "Building Extension"
    BUILDING_PREPARATION = "BUILDING_PREPARATION", "Building Preparation"
    BUILDING_RENOVATION = "BUILDING_RENOVATION", "Building Renovation"
    BUILDING_UPGRADE = "BUILDING_UPGRADE", "Building Upgrade"
    BUILDING_ACTIVATION = "BUILDING_ACTIVATION", "Building Activation"
    DOMAIN_IMPROVEMENT = "DOMAIN_IMPROVEMENT", "Domain Improvement"
    FORTIFICATION_UPGRADE = "FORTIFICATION_UPGRADE", "Fortification Upgrade"
    INTERIOR_DESIGN = "INTERIOR_DESIGN", "Interior Design"
    ROOM_FEATURE_PROGRESSION = "ROOM_FEATURE_PROGRESSION", "Room Feature Progression"
    ROOM_DEFENSE_INSTALLATION = "ROOM_DEFENSE_INSTALLATION", "Room Defense Installation"
    RESEARCH = "RESEARCH", "Research"
    RANSOM = "RANSOM", "Ransom"
    SHIP_CONSTRUCTION = "SHIP_CONSTRUCTION", "Ship Construction"
    SHIP_UPGRADE = "SHIP_UPGRADE", "Ship Upgrade"
    SHIP_REPAIR = "SHIP_REPAIR", "Ship Repair"
    TEST_KIND = "TEST_KIND", "Test Kind (framework tests only)"
    GANG_TURF = "GANG_TURF", "Gang Turf"
    ORGANIZATION_CAPABILITY = "ORGANIZATION_CAPABILITY", "Organization Capability"
    # Money→prestige sink: the only kind whose completion fires a renown award
    # (#1621). Details model + handler live in world.societies (mirroring how
    # captivity owns RANSOM); instant-completion like RANSOM.
    PROPAGANDA = "PROPAGANDA", "Propaganda Campaign"
    CITY_DEFENSE = "CITY_DEFENSE", "City Defense"
    FRAME_JOB = "FRAME_JOB", "Frame Job"
    WAR_FUNDING = "WAR_FUNDING", "War Funding"
    CLEANUP = "CLEANUP", "Area Cleanup"


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
    MISSION = "MISSION", "Mission"


class ContributionPrivacy(models.TextChoices):
    """Whether a contribution's intent text is visible to others."""

    PRIVATE = "PRIVATE", "Private (actor only)"
    GROUP = "GROUP", "Group (all project contributors)"
