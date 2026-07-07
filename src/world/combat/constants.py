"""
Constants and enums for the combat system.

TextChoices are defined here rather than in models.py to avoid circular
import issues when serializers need to reference them.
"""

from django.db import models

# Canonical physical/social/mental axis lives in actions.constants;
# re-exported here for combat-local imports (explicit alias = intentional re-export).
from actions.constants import (
    ActionCategory as ActionCategory,  # noqa: PLC0414
)
from world.gm.constants import GMLevel

# ---------------------------------------------------------------------------
# Encounter enums
# ---------------------------------------------------------------------------


class EncounterType(models.TextChoices):
    """The type of combat encounter."""

    PARTY_COMBAT = "party_combat", "Party Combat"
    OPEN_ENCOUNTER = "open_encounter", "Open Encounter"
    DUEL = "duel", "Duel"


class EncounterOutcome(models.TextChoices):
    """Typed result recorded when an encounter completes (#876)."""

    VICTORY = "victory", "Victory"
    DEFEAT = "defeat", "Defeat"
    FLED = "fled", "Fled"
    ABANDONED = "abandoned", "Abandoned"


class RiskLevel(models.TextChoices):
    """How dangerous the encounter is for participants."""

    LOW = "low", "Low"
    MODERATE = "moderate", "Moderate"
    HIGH = "high", "High"
    EXTREME = "extreme", "Extreme"
    LETHAL = "lethal", "Lethal"


# Risk levels that require a target's explicit acknowledgement before a hostile
# cast can pull them into an existing encounter (#777). Only EXTREME and LETHAL
# gate; LOW/MODERATE/HIGH do not (fresh cast-seeded encounters are MODERATE).
RISK_LEVELS_REQUIRING_ACKNOWLEDGEMENT: frozenset[RiskLevel] = frozenset(
    {RiskLevel.EXTREME, RiskLevel.LETHAL}
)


class StakesLevel(models.TextChoices):
    """Narrative scope of the encounter's consequences."""

    LOCAL = "local", "Local"
    REGIONAL = "regional", "Regional"
    NATIONAL = "national", "National"
    CONTINENTAL = "continental", "Continental"
    WORLD = "world", "World"


class SurgeTriggerKind(models.TextChoices):
    """What dramatic beat produced a DramaticSurgeRecord (#2013)."""

    ALLY_FALLEN = "ally_fallen", "Ally Fallen"
    ALLY_PERIL = "ally_peril", "Ally In Peril"
    HATED_FOE = "hated_foe", "Hated Foe"
    HIGH_STAKES = "high_stakes", "High Stakes"


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


class CombatManeuver(models.TextChoices):
    """Special non-technique declarations a PC can make for a round."""

    FLEE = "flee", "Flee"
    COVER = "cover", "Cover"
    YIELD = "yield", "Yield"
    INTERPOSE = "interpose", "Interpose"
    SUCCOR = "succor", "Succor"


class DuelChallengeStatus(models.TextChoices):
    """Lifecycle of a PC-vs-PC duel challenge."""

    PENDING = "pending", "Pending"
    ACCEPTED = "accepted", "Accepted"
    DECLINED = "declined", "Declined"
    WITHDRAWN = "withdrawn", "Withdrawn"
    EXPIRED = "expired", "Expired"


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


class CombatAllegiance(models.TextChoices):
    """Which side a combatant fights on. Mutable: charm/switch-sides flips it."""

    ENEMY = "enemy", "Enemy"
    ALLY = "ally", "Ally"


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
# Penetration-vs-resistance contest (#639)
#
# Name of the seeded CheckType the caster rolls to penetrate a warded
# opponent's barrier. Penetration difficulty == the target's
# CombatOpponent.barrier_strength (the ward only — NOT damage-type resistance,
# which is soaked once in apply_damage_to_opponent). The check's success level
# selects a power factor from conditions.PenetrationOutcomeFactor.
# ---------------------------------------------------------------------------

PENETRATION_CHECK_TYPE_NAME: str = "penetration"

# ---------------------------------------------------------------------------
# Flee-check wiring (#878)
#
# Name of the seeded CheckType rolled for flee attempts. Difficulty is
# FleeConfig.base_difficulty plus the max FleeTierModifier over active
# opponents; cover_bonus is added per ally covering this round.
# ---------------------------------------------------------------------------

FLEE_CHECK_TYPE_NAME: str = "flee"
FLEE_BASE_DIFFICULTY: int = 15
FLEE_COVER_BONUS: int = 10

# PARTIAL's authored success_level. At or above it the fleer escapes; at or
# below it the selected pool consequence applies (PARTIAL = escape at a cost;
# FAILURE/BOTCH = stays in the fight, consequence still lands).
FLEE_PARTIAL_SUCCESS_LEVEL: int = -1

# ---------------------------------------------------------------------------
# Interpose
# ---------------------------------------------------------------------------

# Base fatigue cost charged to the interposer ONLY when the interpose fires
# (i.e. dispatch_interpose returns a result). Armed-but-never-triggered
# interpose declarations cost nothing. Scaled by the action's effort_level
# multiplier inside apply_fatigue (same formula as other combat actions).
INTERPOSE_BASE_FATIGUE_COST: int = 3

# ---------------------------------------------------------------------------
# Succor (#1744)
# ---------------------------------------------------------------------------

# Base fatigue cost charged to the succorer ONLY the first time Succor resolves
# this round (fatigue is charged once per round, not once per hazard row — a
# Succor declaration protects the target against every round-ticked hazard that
# round, per the approved spec's Decision 8). Mirrors INTERPOSE_BASE_FATIGUE_COST.
SUCCOR_BASE_FATIGUE_COST: int = 3

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


# ---------------------------------------------------------------------------
# Encounter scaling defaults (#566)
#
# These dicts seed OpponentTierTemplate, RiskScalingModifier, and
# StakesLevelRequirement via seed_scaling_defaults() in factories.py.
# All values are tunable by staff through admin; these are the authored
# starting points.
# ---------------------------------------------------------------------------

# Per-tier stat defaults.  SWARM uses count/body mechanics; base_health is 0
# because individual bodies have toughness, not a single HP pool.
DEFAULT_TIER_TEMPLATES: dict[str, dict] = {
    OpponentTier.SWARM: {
        "base_health": 0,
        "base_soak": 0,
        "base_probing_threshold": None,
        "base_swarm_count": 20,
        "body_toughness": 5,
        "bodies_per_attack": 4,
        "barrier_strength": None,
        "boss_phase_count": 1,
    },
    OpponentTier.MOOK: {
        "base_health": 30,
        "base_soak": 0,
        "base_probing_threshold": None,
        "base_swarm_count": None,
        "body_toughness": None,
        "bodies_per_attack": None,
        "barrier_strength": None,
        "boss_phase_count": 1,
    },
    OpponentTier.ELITE: {
        "base_health": 80,
        "base_soak": 3,
        "base_probing_threshold": None,
        "base_swarm_count": None,
        "body_toughness": None,
        "bodies_per_attack": None,
        "barrier_strength": None,
        "boss_phase_count": 1,
    },
    OpponentTier.BOSS: {
        "base_health": 300,
        "base_soak": 8,
        "base_probing_threshold": 5,
        "base_swarm_count": None,
        "body_toughness": None,
        "bodies_per_attack": None,
        "barrier_strength": None,  # authored per-fight
        "boss_phase_count": 3,
    },
    OpponentTier.HERO_KILLER: {
        "base_health": 9999,
        "base_soak": 50,
        "base_probing_threshold": 30,
        "base_swarm_count": None,
        "body_toughness": None,
        "bodies_per_attack": None,
        "barrier_strength": None,
        "boss_phase_count": 1,
    },
}

# Risk multipliers: how much to scale stat budgets up/down by encounter danger.
DEFAULT_RISK_MULTIPLIERS: dict[str, str] = {
    RiskLevel.LOW: "0.70",
    RiskLevel.MODERATE: "1.00",
    RiskLevel.HIGH: "1.30",
    RiskLevel.EXTREME: "1.60",
    RiskLevel.LETHAL: "2.00",
}

# Stakes requirements: minimum party level + GM level (world.gm.constants.GMLevel)
# to run at that scope.
#
# Format: stakes_level → {"minimum_party_average_level": int, "minimum_gm_level": GMLevel}
DEFAULT_STAKES_REQUIREMENTS: dict[str, dict] = {
    StakesLevel.LOCAL: {
        "minimum_party_average_level": 0,
        "minimum_gm_level": GMLevel.STARTING,
    },
    StakesLevel.REGIONAL: {
        "minimum_party_average_level": 5,
        "minimum_gm_level": GMLevel.JUNIOR,
    },
    StakesLevel.NATIONAL: {
        "minimum_party_average_level": 10,
        "minimum_gm_level": GMLevel.GM,
    },
    StakesLevel.CONTINENTAL: {
        "minimum_party_average_level": 15,
        "minimum_gm_level": GMLevel.EXPERIENCED,
    },
    StakesLevel.WORLD: {
        "minimum_party_average_level": 20,
        "minimum_gm_level": GMLevel.SENIOR,
    },
}

# EncounterScalingConfig singleton defaults.
SCALING_CONFIG_BASELINE_PARTY_SIZE: int = 4
SCALING_CONFIG_PER_EXTRA_MEMBER_PCT: str = "0.15"
SCALING_CONFIG_PER_AVG_LEVEL_PCT: str = "0.05"
