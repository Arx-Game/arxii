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


class UnitComposition(models.TextChoices):
    INFANTRY = "infantry", "Infantry"
    CAVALRY = "cavalry", "Cavalry"
    ARCHERS = "archers", "Archers"
    SIEGE = "siege", "Siege"
    FLYING = "flying", "Flying"
    NAVAL = "naval", "Naval"
    MAGICAL = "magical", "Magical"
    IRREGULAR = "irregular", "Irregular"


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
