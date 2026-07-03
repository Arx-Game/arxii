"""Battle system enums and tuning constants."""

from django.db import models


class BattleSideRole(models.TextChoices):
    ATTACKER = "attacker", "Attacker"
    DEFENDER = "defender", "Defender"


class BattleUnitStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    ROUTED = "routed", "Routed"
    DESTROYED = "destroyed", "Destroyed"


class BattleParticipantStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    WITHDRAWN = "withdrawn", "Withdrawn"
    INCAPACITATED = "incapacitated", "Incapacitated"


class UnitQuality(models.TextChoices):
    MILITIA = "militia", "Militia"
    LEVY = "levy", "Levy"
    TRAINED = "trained", "Trained"
    VETERAN = "veteran", "Veteran"
    ELITE = "elite", "Elite"


class TerrainType(models.TextChoices):
    OPEN = "open", "Open"
    DIFFICULT = "difficult", "Difficult"
    FORTIFIED = "fortified", "Fortified"
    ELEVATED = "elevated", "Elevated"
    FLOODED = "flooded", "Flooded"
    URBAN = "urban", "Urban"


class BattlePosture(models.TextChoices):
    BALANCED = "balanced", "Balanced"
    AGGRESSIVE = "aggressive", "Aggressive"
    DEFENSIVE = "defensive", "Defensive"


class BattleActionKind(models.TextChoices):
    STRIKE = "strike", "Strike a unit"
    SUPPORT = "support", "Support an ally"
    RESCUE = "rescue", "Rescue a surrounded ally"
    ROUT = "rout", "Rout an enemy unit"
    RALLY = "rally", "Rally an ally"
    REPEL = "repel", "Repel an attack"
    HOLD = "hold", "Hold or seize an objective"


class BattleActionScope(models.TextChoices):
    """Targeting breadth of a battle-round declaration (#1710).

    UNIT is the pre-existing default (a single BattleUnit/BattleParticipant).
    PLACE/SIDE require the declaring participant to hold the matching
    command_tier — see world.battles.services.declare_battle_action.
    """

    UNIT = "unit", "Unit"
    PLACE = "place", "Place (front-wide)"
    SIDE = "side", "Side (army-wide)"


class BattleOutcome(models.TextChoices):
    UNRESOLVED = "unresolved", "Unresolved"
    ATTACKER_DECISIVE = "attacker_decisive", "Attacker — decisive"
    ATTACKER_MARGINAL = "attacker_marginal", "Attacker — marginal"
    DEFENDER_MARGINAL = "defender_marginal", "Defender — marginal"
    DEFENDER_DECISIVE = "defender_decisive", "Defender — decisive"


DEFAULT_VICTORY_THRESHOLD = 100
DEFAULT_ROUND_LIMIT = 10
STRIKE_ATTRITION_PER_LEVEL = 10
STRIKE_VP_PER_LEVEL = 5
SUPPORT_VP = 3
BASE_FAILURE_DAMAGE = 8
DECISIVE_MARGIN = 50
ROUTED_STRENGTH_THRESHOLD = 30

# Morale — a second BattleUnit resource alongside strength (#1712). Unlike strength
# (starts at its ceiling, only depletes), morale starts well below its ceiling and
# climbing it is comparatively hard — sitting near MAX_MORALE reads as "fanatical,"
# not baseline. status is always DERIVED from strength+morale jointly (see
# world.battles.resolution._compute_unit_status) — never written independently.
DEFAULT_MORALE = 70
MAX_MORALE = 100
ROUTED_MORALE_THRESHOLD = 25

# Battle-flow action tuning (#1712). ROUT/RALLY scale with success_level exactly
# like STRIKE's attrition; REPEL/HOLD award flat VP like SUPPORT (they don't move a
# numeric resource). All values here are tuning — adjust freely during playtesting.
ROUT_MORALE_PER_LEVEL = 15
RALLY_MORALE_PER_LEVEL = 15
ROUT_VP_PER_LEVEL = 4
RALLY_VP = 3
REPEL_VP = 4
HOLD_CAPTURE_VP = 8
HOLD_SUSTAIN_VP = 3
REPEL_DEFENSE_BONUS = 15

# Surrounded entry-roll signal weights (#1733). Fed as perform_check extra_modifiers
# for the entry roll (Task 6) — authored content (the surrounded_entry pool's rows)
# decides the actual odds; these are inputs to that roll, not a code-level gate.
SURROUNDED_ENTRY_ISOLATED_MODIFIER = -15  # isolated: no ally at your BattlePlace
SURROUNDED_ENTRY_MOBILITY_MODIFIER = 40  # active, unimpaired MOVEMENT capability

# Attacker-facing flat check modifier per unit quality (#1711). Higher quality
# units are more disciplined/well-drilled — harder to land a clean STRIKE on.
UNIT_QUALITY_STRIKE_MODIFIER: dict[str, int] = {
    UnitQuality.MILITIA: 10,
    UnitQuality.LEVY: 5,
    UnitQuality.TRAINED: 0,
    UnitQuality.VETERAN: -10,
    UnitQuality.ELITE: -20,
}

# Posture (#1711) trades VP-gain speed against check difficulty and failure
# damage. Percent scaling applied to STRIKE_VP_PER_LEVEL / SUPPORT_VP gains;
# flat modifiers applied to the STRIKE check and to BASE_FAILURE_DAMAGE.
BATTLE_POSTURE_VP_MULTIPLIER: dict[str, float] = {
    BattlePosture.BALANCED: 1.0,
    BattlePosture.AGGRESSIVE: 1.4,
    BattlePosture.DEFENSIVE: 0.7,
}
BATTLE_POSTURE_CHECK_MODIFIER: dict[str, int] = {
    BattlePosture.BALANCED: 0,
    BattlePosture.AGGRESSIVE: -5,
    BattlePosture.DEFENSIVE: 10,
}
BATTLE_POSTURE_FAILURE_DAMAGE_MODIFIER: dict[str, int] = {
    BattlePosture.BALANCED: 0,
    BattlePosture.AGGRESSIVE: 4,
    BattlePosture.DEFENSIVE: -4,
}

# Idempotent-seed target name for the commander-bonus modifier walk (#1711).
# category="stat" (already EQUIPMENT_RELEVANT_CATEGORIES) so covenant-role /
# facet / mantle bonuses authored against it flow through the existing walk.
BATTLE_COMMAND_TARGET_NAME = "battle_command"
