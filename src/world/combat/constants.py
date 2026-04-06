"""
Constants and enums for the combat system.

TextChoices are defined here rather than in models.py to avoid circular
import issues when serializers need to reference them.
"""

from django.db import models

# ---------------------------------------------------------------------------
# Encounter enums
# ---------------------------------------------------------------------------


class EncounterType(models.TextChoices):
    """The type of combat encounter."""

    PARTY_COMBAT = "party_combat", "Party Combat"
    OPEN_ENCOUNTER = "open_encounter", "Open Encounter"


class EncounterStatus(models.TextChoices):
    """Lifecycle status of a combat encounter."""

    DECLARING = "declaring", "Declaring"
    RESOLVING = "resolving", "Resolving"
    BETWEEN_ROUNDS = "between_rounds", "Between Rounds"
    COMPLETED = "completed", "Completed"


class RiskLevel(models.TextChoices):
    """How dangerous the encounter is for participants."""

    LOW = "low", "Low"
    MODERATE = "moderate", "Moderate"
    HIGH = "high", "High"
    EXTREME = "extreme", "Extreme"
    LETHAL = "lethal", "Lethal"


class StakesLevel(models.TextChoices):
    """Narrative scope of the encounter's consequences."""

    LOCAL = "local", "Local"
    REGIONAL = "regional", "Regional"
    NATIONAL = "national", "National"
    CONTINENTAL = "continental", "Continental"
    WORLD = "world", "World"


# ---------------------------------------------------------------------------
# Opponent enums
# ---------------------------------------------------------------------------


class OpponentTier(models.TextChoices):
    """Power tier of an NPC opponent."""

    SWARM = "swarm", "Swarm"
    MOOK = "mook", "Mook"
    ELITE = "elite", "Elite"
    BOSS = "boss", "Boss"
    HERO_KILLER = "hero_killer", "Hero Killer"


class OpponentStatus(models.TextChoices):
    """Current status of an opponent in an encounter."""

    ACTIVE = "active", "Active"
    DEFEATED = "defeated", "Defeated"
    FLED = "fled", "Fled"


# ---------------------------------------------------------------------------
# Participant enums
# ---------------------------------------------------------------------------


class ParticipantStatus(models.TextChoices):
    """Current status of a PC participant in combat."""

    ACTIVE = "active", "Active"
    UNCONSCIOUS = "unconscious", "Unconscious"
    DYING = "dying", "Dying"
    DEAD = "dead", "Dead"


# ---------------------------------------------------------------------------
# Action enums
# ---------------------------------------------------------------------------


class ActionCategory(models.TextChoices):
    """Broad category of a combat action."""

    PHYSICAL = "physical", "Physical"
    SOCIAL = "social", "Social"
    MENTAL = "mental", "Mental"


class TargetingMode(models.TextChoices):
    """How many targets an action affects."""

    SINGLE = "single", "Single"
    MULTI = "multi", "Multi"
    ALL = "all", "All"


class TargetSelection(models.TextChoices):
    """How an NPC selects its target."""

    RANDOM = "random", "Random"
    HIGHEST_THREAT = "highest_threat", "Highest Threat"
    LOWEST_HEALTH = "lowest_health", "Lowest Health"
    SPECIFIC_ROLE = "specific_role", "Specific Role"


# ---------------------------------------------------------------------------
# Speed ranks — lower means faster.
#
# Covenant roles and their speed mappings live in world.covenants.
# Combat stores a denormalized base_speed_rank per participant; these
# constants provide the fallback defaults for PCs without a role.
# ---------------------------------------------------------------------------

NO_ROLE_SPEED_RANK: int = 20
NPC_SPEED_RANK: int = 15

# ---------------------------------------------------------------------------
# Health thresholds
# ---------------------------------------------------------------------------

PERMANENT_WOUND_THRESHOLD: float = 0.5
KNOCKOUT_HEALTH_THRESHOLD: float = 0.2
DEATH_HEALTH_THRESHOLD: int = 0

# ---------------------------------------------------------------------------
# Wound descriptions — (threshold, description) from healthiest to worst
# ---------------------------------------------------------------------------

WOUND_DESCRIPTIONS: list[tuple[float, str]] = [
    (0.9, "healthy appearance"),
    (0.8, "lightly wounded"),
    (0.7, "wounded"),
    (0.6, "moderately wounded"),
    (0.5, "seriously wounded"),
    (0.4, "badly wounded"),
    (0.3, "critically wounded"),
    (0.2, "near collapse"),
    (0.1, "barely clinging to life"),
    (0.0, "incapacitated"),
]
