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

# #2051 — the combo invariant: combos are never solo. A combo definition must
# have at least this many slots, each filled by a distinct PC-controlled action.
COMBO_MIN_SLOTS: int = 2


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
    INTERFERENCE = "interference", "Interference"


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
    ENGAGE = "engage", "Engage"
    DISENGAGE = "disengage", "Disengage"
    RALLY = "rally", "Rally"
    DEMORALIZE = "demoralize", "Demoralize"
    TAUNT = "taunt", "Taunt"
    PARLEY = "parley", "Parley"
    USE_ITEM = "use_item", "Use Item"
    CHARGE = "charge", "Charge"
    JOUST = "joust", "Joust"


# ---------------------------------------------------------------------------
# Mounted combat (#1843) — CHARGE/JOUST flat bonuses + JOUST margin bands.
# ---------------------------------------------------------------------------

# Flat check/damage bonuses for a CHARGE maneuver (doubled when the attacker's
# equipped weapon is GearArchetype.LANCE).
CHARGE_CHECK_BONUS: int = 10
CHARGE_DAMAGE_BONUS: int = 5

# Flat check penalty for attacking with a LANCE-archetype weapon while not
# Mounted — applies to any attack, not just CHARGE/JOUST.
LANCE_UNMOUNTED_PENALTY: int = -10

# Max hops a CHARGE may cover — generous but bounded (mirrors technique
# REACH_N's reach_hops parameter).
CHARGE_MAX_HOPS: int = 5

# success_level gap bands for a JOUST's opposed pass. A gap >= DECISIVE is a
# clean unhorsing; a gap >= NARROW (but < DECISIVE) lands a lesser hit; a gap
# of 0 is a tie (both jarred, no damage).
JOUST_DECISIVE_MARGIN: int = 2
JOUST_NARROW_MARGIN: int = 1


class EngagementLockStatus(models.TextChoices):
    """Lifecycle status of an EngagementLock (#2020)."""

    ACTIVE = "active", "Active"
    BROKEN = "broken", "Broken"
    ENDED = "ended", "Ended"


class LockInitiator(models.TextChoices):
    """How an engagement lock was formed (#2020)."""

    THREAT = "threat", "Threat Threshold"
    PC_CHALLENGE = "pc_challenge", "PC Challenge"
    GM_DECLARED = "gm_declared", "GM Declared"


class LockBreakReason(models.TextChoices):
    """Why an engagement lock ended (#2020)."""

    DEFEAT = "defeat", "Opponent Defeated"
    FLEE = "flee", "Locked PC Fled"
    DISENGAGE = "disengage", "Deliberate Disengage"
    INTERFERENCE = "interference", "Interference Defeated"
    EXPIRED = "expired", "Expired"


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


class StrikeDelivery(models.TextChoices):
    """How a ThreatPoolEntry's strike reaches its target (#2209 rampart interception)."""

    MELEE = "melee", "Melee"
    MISSILE = "missile", "Missile"


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


# Flat resonance amount granted per participant on first-ever combo discovery (#2017).
COMBO_DISCOVERY_GRANT: int = 10


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
# Elevation advantage (#2011)
#
# Name of the seeded ModifierTarget for the offensive-only elevation bonus.
# When an attacker is at an ELEVATED or AERIAL position and the target is
# not, this flat bonus feeds into the combat check's extra_modifiers.
# Lives in the 'stat' category (same as weapon_damage/armor_soak).
# ---------------------------------------------------------------------------

ELEVATION_ADVANTAGE_TARGET_NAME: str = "elevation_advantage"

# ---------------------------------------------------------------------------
# Interpose
# ---------------------------------------------------------------------------

# Base fatigue cost charged to the interposer ONLY when the interpose fires
# (i.e. dispatch_interpose returns a result). Armed-but-never-triggered
# interpose declarations cost nothing. Scaled by the action's effort_level
# multiplier inside apply_fatigue (same formula as other combat actions).
INTERPOSE_BASE_FATIGUE_COST: int = 3

# ---------------------------------------------------------------------------
# Reaction economy (#2639)
# ---------------------------------------------------------------------------

# How many reactions (e.g. INTERPOSE fires) a single CombatParticipant may
# spend per round. Gated + incremented at the reaction fire seam
# (_dispatch_interpose_action); reset to 0 for every participant in
# begin_declaration_phase. A second declared reaction this round declines
# with the same "did not fire" shape as an unaffordable/failed one.
REACTIONS_PER_ROUND: int = 1

# Per-moment absorption cap: how many interceptors may answer ONE
# DamagePreApplyPayload (one landing hit) before further interceptors
# decline, tracked via DamagePreApplyPayload.answers_consumed. Standing
# defenses (absorb/reflect/blink conditions) are deliberately outside this
# cap — they carry their own reactive costs (flagged judgment call).
ABSORPTION_CAP_PER_MOMENT: int = 2

# ---------------------------------------------------------------------------
# Telegraphed enemy wind-ups (#2637)
# ---------------------------------------------------------------------------

# downgrades >= this many fully cancels a winding-up attack (the "perfect
# chain" — wreck is a downgrade, cancel is earned, never automatic).
WINDUP_FIZZLE_DOWNGRADES: int = 3

# Each interception downgrade scales matured damage down by this fraction
# (x(1 - WINDUP_DOWNGRADE_STEP * downgrades)), floored at
# WINDUP_MIN_DAMAGE_SCALE.
WINDUP_DOWNGRADE_STEP: float = 0.25
WINDUP_MIN_DAMAGE_SCALE: float = 0.25

# A called-out wind-up's interception adds this many downgrades per landing
# hit instead of the blind default of 1 (called-out beats blind, F-6c).
WINDUP_CALLED_OUT_DOWNGRADE: int = 2
WINDUP_BLIND_DOWNGRADE: int = 1

# Fallback telegraph text when ThreatPoolEntry.windup_telegraph is blank.
# {opponent} is substituted with the opponent's display name.
WINDUP_GENERIC_TELEGRAPH: str = "{opponent} begins something enormous..."

# ---------------------------------------------------------------------------
# Succor (#1744)
# ---------------------------------------------------------------------------

# Base fatigue cost charged to the succorer ONLY the first time Succor resolves
# this round (fatigue is charged once per round, not once per hazard row — a
# Succor declaration protects the target against every round-ticked hazard that
# round, per the approved spec's Decision 8). Mirrors INTERPOSE_BASE_FATIGUE_COST.
SUCCOR_BASE_FATIGUE_COST: int = 3

# ---------------------------------------------------------------------------
# Party-NPC morale (#2015)
#
# A first-class depletable resource on CombatOpponent, mirroring war-scale
# BattleUnit.morale (battles/constants.py:119). status is DERIVED via
# morale_state_for (world.combat.morale) — never stored. Mindless opponents
# (OpponentTierTemplate.has_morale=False) impose MINDLESS_MORALE_RESISTANCE on
# morale checks, not an immunity — a powerful enough roll breaks through (Arx's
# "power can do the impossible" tenet).
# ---------------------------------------------------------------------------
DEFAULT_OPPONENT_MORALE: int = 70
MAX_OPPONENT_MORALE: int = 100
FALTER_MORALE_THRESHOLD: int = 50  # at/below: faltering
BREAK_MORALE_THRESHOLD: int = 25  # at/below: broken -> FLED

# Party-scale social-combat tuning (#2015). Values mirror the war-scale
# ROUT/RALLY per-level magnitudes (battles/constants.py:131); adjust freely
# during playtesting.
DEMORALIZE_MORALE_PER_LEVEL: int = 15
RALLY_MORALE_PER_LEVEL: int = 15
TAUNT_THREAT_PER_LEVEL: int = 25
RALLY_BASE_DIFFICULTY: int = 10
PARLEY_DISPOSITION_FLOOR: int = 20
MINDLESS_MORALE_RESISTANCE: int = 30

# Success-level thresholds for social-combat verb outcomes (#2015).
RALLY_GREAT_SUCCESS_LEVEL: int = 3  # great success: restore ally morale
PARLEY_DECISIVE_SUCCESS_LEVEL: int = 3  # decisive: calm the opponent
PARLEY_CRITICAL_SUCCESS_LEVEL: int = 5  # critical + broken: NPC yields

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


# ---------------------------------------------------------------------------
# Wind-as-mechanic (#1555) — the combat consumer of the WIND exposure axis
# (world.locations.services.felt_exposure, StatKey.WIND, #1522). Bands are
# authored thresholds on felt WIND, not raw per-point scaling — raw scaling
# was rejected as illegible (see ADR — docs/adr/).
# ---------------------------------------------------------------------------

WIND_BAND_BREEZY_THRESHOLD: int = 15
WIND_BAND_WINDY_THRESHOLD: int = 40
WIND_BAND_GALE_THRESHOLD: int = 70

WIND_PENALTY_BREEZY: int = -5
WIND_PENALTY_WINDY: int = -10
WIND_PENALTY_GALE: int = -20


def wind_penalty(felt: int) -> int:
    """The missile check penalty for a room's felt WIND exposure (#1555).

    Banded, not linear: CALM (<15) -> 0, BREEZY (15-39) -> -5, WINDY (40-69) -> -10,
    GALE (70+) -> -20. Pure function of the already-resolved felt exposure value
    (``world.locations.services.felt_exposure``) — no room/DB access here, so callers
    control when the (enclosure-gated) exposure lookup happens.
    """
    if felt >= WIND_BAND_GALE_THRESHOLD:
        return WIND_PENALTY_GALE
    if felt >= WIND_BAND_WINDY_THRESHOLD:
        return WIND_PENALTY_WINDY
    if felt >= WIND_BAND_BREEZY_THRESHOLD:
        return WIND_PENALTY_BREEZY
    return 0
