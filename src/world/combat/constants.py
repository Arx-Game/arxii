"""
Constants and enums for the combat system.

TextChoices are defined here rather than in models.py to avoid circular
import issues when serializers need to reference them.
"""

from django.db import models

# Canonical physical/social/mental axis lives in actions.constants;
# re-exported here for combat-local imports (explicit alias = intentional re-export).
from actions.constants import (
    ActionCategory as ActionCategory,  # noqa: PLC0414 — re-export converged canonical enum for combat-local imports
)

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


class PaceMode(models.TextChoices):
    """How round timing is managed."""

    TIMED = "timed", "Timed"
    READY = "ready", "Ready"
    MANUAL = "manual", "Manual"


class ParticipantStatus(models.TextChoices):
    """Current status of a PC participant in an encounter."""

    ACTIVE = "active", "Active"
    FLED = "fled", "Fled"
    REMOVED = "removed", "Removed"


DEFAULT_PACE_TIMER_MINUTES: int = 10


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
# Action enums
# ---------------------------------------------------------------------------


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
# Entity type identifiers for resolution order
# ---------------------------------------------------------------------------

ENTITY_TYPE_PC: str = "pc"
ENTITY_TYPE_NPC: str = "npc"

# ---------------------------------------------------------------------------
# Speed ranks — lower means faster.
#
# Covenant roles define speed_rank (world.covenants). PCs without a role
# resolve at NO_ROLE_SPEED_RANK. NPCs resolve at NPC_SPEED_RANK.
# ---------------------------------------------------------------------------

NO_ROLE_SPEED_RANK: int = 20
NPC_SPEED_RANK: int = 15

# ---------------------------------------------------------------------------
# Combo learning methods
# ---------------------------------------------------------------------------


class ComboLearningMethod(models.TextChoices):
    """How a character learned a combo."""

    TRAINING = "training", "Training"
    COMBAT = "combat", "Combat"
    RESEARCH = "research", "Research"


# ---------------------------------------------------------------------------
# Defensive check damage multipliers
#
# Maps success_level from perform_check to a damage multiplier.
# success_level >= 2: no damage (great success)
# success_level == 1: reduced damage (partial success)
# success_level == 0: full damage (failure)
# success_level <= -1: extra damage (critical failure)
# ---------------------------------------------------------------------------

DEFENSE_NO_DAMAGE_THRESHOLD: int = 2
DEFENSE_REDUCED_THRESHOLD: int = 1
DEFENSE_REDUCED_MULTIPLIER: float = 0.5
DEFENSE_FULL_MULTIPLIER: float = 1.0
DEFENSE_CRITICAL_MULTIPLIER: float = 1.5

# ---------------------------------------------------------------------------
# Offensive check damage scaling
#
# Maps success_level from perform_check to damage outcome for PC attacks.
# success_level >= OFFENSE_FULL_THRESHOLD: full base_power
# success_level >= OFFENSE_HALF_THRESHOLD: half base_power
# success_level < OFFENSE_HALF_THRESHOLD: miss (0 damage)
# ---------------------------------------------------------------------------

OFFENSE_FULL_THRESHOLD: int = 2
OFFENSE_HALF_THRESHOLD: int = 1

# ---------------------------------------------------------------------------
# Clash enums
# ---------------------------------------------------------------------------


class ClashFlavor(models.TextChoices):
    """Which variant of the Clash mechanic this instance represents."""

    CLASH = "CLASH", "Clash"
    LOCK = "LOCK", "Lock"
    WARD = "WARD", "Ward"
    BREAK = "BREAK", "Break"


class LockPcRole(models.TextChoices):
    """A PC's role within a LOCK-flavored Clash."""

    SUSTAINING = "SUSTAINING", "Sustaining"
    ESCAPING = "ESCAPING", "Escaping"


class ClashStatus(models.TextChoices):
    """Lifecycle status of a Clash."""

    ACTIVE = "ACTIVE", "Active"
    RESOLVED = "RESOLVED", "Resolved"


class ClashActionSlot(models.TextChoices):
    """Which action slot a PC commits to a Clash each round."""

    FOCUSED = "FOCUSED", "Focused"
    PASSIVE = "PASSIVE", "Passive"


class ClashResolution(models.TextChoices):
    """Outcome tier when a Clash resolves.

    CLASH uses all five tiers (PC_DECISIVE … NPC_DECISIVE) plus ABANDONED.
    BREAK uses PC_DECISIVE, PC_MARGINAL, and ABANDONED.
    LOCK and WARD map onto subsets of these values.
    """

    PC_DECISIVE = "PC_DECISIVE", "PC Decisive"
    PC_MARGINAL = "PC_MARGINAL", "PC Marginal"
    MUTUAL = "MUTUAL", "Mutual"
    NPC_MARGINAL = "NPC_MARGINAL", "NPC Marginal"
    NPC_DECISIVE = "NPC_DECISIVE", "NPC Decisive"
    ABANDONED = "ABANDONED", "Abandoned"
