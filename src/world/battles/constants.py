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
    WATER = "water", "Open water"
    AERIAL = "aerial", "Open sky"


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
    BREACH = "breach", "Breach a fortification"
    FORTIFY = "fortify", "Fortify a structure"
    SET_ENVIRONMENT = "set_environment", "Set battlefield weather"
    REPOSITION = "reposition", "Reposition a vehicle"
    MOVE = "move", "Move to a front"


class BattleActionScope(models.TextChoices):
    """Targeting breadth of a battle-round declaration (#1710).

    UNIT is the pre-existing default (a single BattleUnit/BattleParticipant).
    PLACE/SIDE/BATTLE require the declaring participant to hold the matching
    command_tier — see world.battles.services.declare_battle_action.
    BATTLE is the widest scope (#1715) — no unit/place/side target, affects
    the whole Battle; gated at the same SUPREME tier as SIDE.
    """

    UNIT = "unit", "Unit"
    PLACE = "place", "Place (front-wide)"
    SIDE = "side", "Side (army-wide)"
    BATTLE = "battle", "Battle (whole-battle-wide)"


class FortificationKind(models.TextChoices):
    """Descriptive/authoring axis for a Fortification (#1713).

    Purely descriptive plus a base-integrity lookup — BREACH/FORTIFY behave
    identically regardless of kind in this MVP (see docs/adr/0083).
    """

    WALL = "wall", "Wall"
    GATE = "gate", "Gate"
    BATTLEMENT = "battlement", "Battlement"
    HULL = "hull", "Hull"


class VehicleKind(models.TextChoices):
    """The concrete flavor a BattleVehicle represents (#1714)."""

    SHIP = "ship", "Naval ship"
    AIRSHIP = "airship", "Airship"
    DRAGON = "dragon", "Dragon"
    KRAKEN = "kraken", "Kraken"
    COMPANION = "companion", "Companion"


class BattleOutcome(models.TextChoices):
    UNRESOLVED = "unresolved", "Unresolved"
    ATTACKER_DECISIVE = "attacker_decisive", "Attacker — decisive"
    ATTACKER_MARGINAL = "attacker_marginal", "Attacker — marginal"
    DEFENDER_MARGINAL = "defender_marginal", "Defender — marginal"
    DEFENDER_DECISIVE = "defender_decisive", "Defender — decisive"


DEFAULT_VICTORY_THRESHOLD = 100
DEFAULT_ROUND_LIMIT = 10
LARGE_SCALE_BATTLE_PARTICIPANT_THRESHOLD = 10
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

# MOVE tuning (#2007). Distance/arrival is bounded by effective MOVEMENT
# capability (see world.battles.resolution._resolve_move_success); movement_cost
# only affects the MOVE technique check's difficulty, not the distance math —
# its first real consumer (previously authored-but-inert, models.py:243).
MOVE_COST_DIFFICULTY_PER_POINT = 5

# Fortification BREACH/FORTIFY tuning (#1713). BREACH scales like STRIKE's attrition
# (both grind a depletable resource); FORTIFY scales like ROUT/RALLY's morale
# movement (both restore/damage a resource by success_level). VP awards mirror
# STRIKE_VP_PER_LEVEL/RALLY_VP's magnitude — BREACH is the "grinding attrition" verb,
# FORTIFY the "restore" verb.
BREACH_INTEGRITY_PER_LEVEL = 10
FORTIFY_INTEGRITY_PER_LEVEL = 15
BREACH_VP_PER_LEVEL = 5
FORTIFY_VP = 3

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

# Fortification (#1713) tuning. BASE_INTEGRITY is a starting ceiling per
# FortificationKind before any persistent investment; FORTIFICATION_LEVEL_INTEGRITY_BONUS
# is a flat per-level ladder bonus (mirrors UNIT_QUALITY_STRIKE_MODIFIER being a flat
# ladder, not a multiplier) applied per Building.fortification_level. A fully-invested
# (MAX_FORTIFICATION_LEVEL, see world.buildings.room_constants) WALL tops out at
# 100 + 5*20 = 200 integrity — always breachable given enough BREACH rounds.
BASE_INTEGRITY: dict[str, int] = {
    FortificationKind.WALL: 100,
    FortificationKind.BATTLEMENT: 80,
    FortificationKind.GATE: 60,
    FortificationKind.HULL: 120,
}
FORTIFICATION_LEVEL_INTEGRITY_BONUS = 20

# SET_ENVIRONMENT tuning (#1715). Duration is always >= 2 rounds since
# success_level >= 1 on any success branch — "stronger cast holds longer"
# (user story 6) can never silently round down to zero effective rounds.
# Flat VP like REPEL/HOLD — SET_ENVIRONMENT doesn't move a numeric resource.
SET_ENVIRONMENT_BASE_ROUNDS = 1
SET_ENVIRONMENT_VP = 4

# Environmental hazard consequence on vehicle destruction (#1714). Abstract
# BattleUnits use a flat authored penalty (no per-unit resistance granularity,
# matching how Property is presence-only for units everywhere else); real PCs
# route through resolve_damage_type_resistance for immunity = high resistance.
VEHICLE_HAZARD_UNIT_STRENGTH_PENALTY = 30
VEHICLE_HAZARD_BASE_DAMAGE = 20

# Win-gated LegendEntry wiring (#2184). Only the winning side mints a Victory
# LegendEvent — DECISIVE outweighs MARGINAL, mirroring DECISIVE_MARGIN's own
# distinction. Standout deeds are a separate, smaller-value pass available to
# BOTH sides (a losing-side rescue is still legend-worthy) — see
# world.battles.legend_wiring.apply_battle_legend_awards.
BATTLE_LEGEND_DECISIVE_VALUE = 25
BATTLE_LEGEND_MARGINAL_VALUE = 12
BATTLE_LEGEND_STANDOUT_VALUE = 15

# success_level > 0 is already "success" (BattleActionDeclaration.success_level
# help_text); STANDOUT_SUCCESS_LEVEL is set clearly above bare success (1) so a
# routine hit doesn't also mint legend — only a standout margin does.
STANDOUT_SUCCESS_LEVEL = 2

# The action kinds dramatic enough to be worth a standout deed on their own,
# independent of who won the battle.
DRAMATIC_KINDS = (
    BattleActionKind.RESCUE,
    BattleActionKind.ROUT,
    BattleActionKind.BREACH,
)
