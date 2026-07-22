"""Constants and enums for the vitals system.

Character life states, health thresholds, and wound descriptions that are
shared across combat, poison, spells, exhaustion, and other systems.
"""

from decimal import Decimal

from django.db import models

# ---------------------------------------------------------------------------
# Character life-state enum
# ---------------------------------------------------------------------------


class CharacterLifeState(models.TextChoices):
    """Mortality axis only. Consciousness/dying live in the conditions system."""

    ALIVE = "alive", "Alive"
    DEAD = "dead", "Dead"


# ---------------------------------------------------------------------------
# Derived wire-status strings
# ---------------------------------------------------------------------------
# Coarse, read-only status surface exposed by the combat API. Derived at read
# time from life_state + active conditions + agency — NOT a persisted field.
# The richer frontend status surface is tracked by #521/#522.

DERIVED_STATUS_DEAD: str = "dead"
DERIVED_STATUS_DYING: str = "dying"
DERIVED_STATUS_INCAPACITATED: str = "incapacitated"
DERIVED_STATUS_ALIVE: str = "alive"


# ---------------------------------------------------------------------------
# Health thresholds
# ---------------------------------------------------------------------------

PERMANENT_WOUND_THRESHOLD: float = 0.5
KNOCKOUT_HEALTH_THRESHOLD: float = 0.2
DEATH_HEALTH_THRESHOLD: float = 0.0

# ---------------------------------------------------------------------------
# Wound descriptions -- (threshold, description) from healthiest to worst
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

# ---------------------------------------------------------------------------
# Survivability check difficulty scaling
# ---------------------------------------------------------------------------

# Base difficulty for knockout check at exactly 20% health
KNOCKOUT_BASE_DIFFICULTY: int = 20
# Additional difficulty per percentage point below 20% health
KNOCKOUT_SCALING_PER_PERCENT: int = 3

# Base difficulty for death check at exactly 0% health
DEATH_BASE_DIFFICULTY: int = 30
# Additional difficulty per percentage point below 0%
DEATH_SCALING_PER_PERCENT: int = 5

# Base difficulty for permanent wound check at exactly 50% damage
WOUND_BASE_DIFFICULTY: int = 15
# Additional difficulty per percentage point of max_health over threshold
WOUND_SCALING_PER_PERCENT: int = 2

# ---------------------------------------------------------------------------
# Wake arc (unconscious recovery) + death off-ramp tuning (#2287)
# ---------------------------------------------------------------------------

# Base difficulty of the per-round wake (Endurance) check at full health
WAKE_BASE_DIFFICULTY: int = 20
# Additional difficulty per percentage point of missing health
WAKE_SCALING_PER_PERCENT: int = 1
# Difficulty eased per round spent unconscious
WAKE_EASE_PER_ROUND: int = 2
# PLACEHOLDER: rounds until guaranteed wake (~10 real minutes at 6s/round)
WAKE_GUARANTEED_ROUNDS: int = 100
# PLACEHOLDER: days after death before a dead character auto-retires
AUTO_RETIRE_DAYS: int = 14

# ---------------------------------------------------------------------------
# Survivability resistance checks (seeded on first use, like fatigue endurance)
# ---------------------------------------------------------------------------

ENDURANCE_CHECK_NAME: str = "Endurance"  # shared: knockout + permanent wound
DEATH_CHECK_NAME: str = "Mortal Resolve"  # distinct, high-stakes (death)
SURVIVABILITY_CHECK_CATEGORY: str = "Survival"

# ---------------------------------------------------------------------------
# Modifier target natural keys
# ---------------------------------------------------------------------------

# Natural-key name for the ModifierTarget used by covenant-role health armor.
# Production code references this by name; tests create the row via
# world.mechanics.factories.max_health_modifier_target().
MAX_HEALTH_MODIFIER_TARGET: str = "max_health"

# ---------------------------------------------------------------------------
# Peril consequence pool natural-key names
# ---------------------------------------------------------------------------

POOL_BLEED_OUT_TERMINAL: str = "bleed_out_terminal"
POOL_ABANDONMENT_ENEMY: str = "abandonment_enemy"
POOL_ABANDONMENT_PVP: str = "abandonment_pvp"
POOL_ABANDONMENT_ENVIRONMENTAL: str = "abandonment_environmental"
POOL_SURROUNDED_ENTRY: str = "surrounded_entry"
POOL_SURROUNDED_TERMINAL_ENEMY: str = "surrounded_terminal_enemy"
POOL_SURROUNDED_TERMINAL_PVP: str = "surrounded_terminal_pvp"

# Global tier pools wired onto VitalsConsequenceConfig by the survivability
# seed cluster (#2287). Names are natural keys.
POOL_KNOCKOUT: str = "knockout"
POOL_DEFAULT_DEATH: str = "default_death"
POOL_DEFAULT_WOUND: str = "default_wound"

# ---------------------------------------------------------------------------
# Bleeding Out stage authoring (#2287) — (stage_order, name, resist_difficulty,
# rounds_to_next). Terminal stage has rounds_to_next=None; its resolution goes
# through the guarded bleed_out_terminal pool, never an unconditional death.
# ---------------------------------------------------------------------------

BLEED_OUT_STAGE_SPECS: list[tuple[int, str, int, int | None]] = [
    (1, "Failing", 15, 2),
    (2, "Slipping Away", 25, 2),
    (3, "At Death's Door", 35, None),
]

# ---------------------------------------------------------------------------
# Liminal dream room (#2287; replaced by the dream realm proper, #2290)
# ---------------------------------------------------------------------------

DREAM_ROOM_KEY: str = "The Threshold of Dreams"
DREAM_ROOM_TAG: str = "dream_liminal"

# ---------------------------------------------------------------------------
# Sleeping condition (#2290 — voluntary sleep for dream entry)
# ---------------------------------------------------------------------------

SLEEPING_CONDITION_NAME: str = "Sleeping"

# Dream Peril consequence pool natural key
POOL_DREAM_PERIL: str = "dream_peril"
DREAM_ROOM_TAG_CATEGORY: str = "system"

# ---------------------------------------------------------------------------
# Wound conditions + double-bounded mend (#2644 — the attrition invariant;
# see ADR-0155 and lore repo design/covenant-vows-consolidated.md §3.1)
# ---------------------------------------------------------------------------

# Names of the three mechanical wound ConditionTemplates authored by
# ensure_wound_conditions(). Vocabulary, not content — see world/vitals/seeds.py.
WOUND_LINGERING_ACHE_NAME: str = "Lingering Ache"
WOUND_CRIPPLING_NAME: str = "Crippling Wound"
WOUND_BLEEDING_NAME: str = "Bleeding Wound"

# The fraction of a wound's causing damage (WoundDetails.damage_taken) that can
# EVER be mended back across every healer who ever tends it — the remainder is
# permanent attrition by design (heals are real but bounded; the party is
# always net-weaker for having fought). Tunable; not wired to an admin config
# field (mirrors PERMANENT_WOUND_THRESHOLD's plain-constant precedent above —
# a game-balance dial, not a per-deploy setting). See mend_wound() in
# world/vitals/services.py and ADR-0155.
NEVER_TO_FULL_FRACTION: Decimal = Decimal("0.75")
