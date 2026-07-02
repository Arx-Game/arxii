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


class BattleActionKind(models.TextChoices):
    STRIKE = "strike", "Strike a unit"
    SUPPORT = "support", "Support an ally"
    RESCUE = "rescue", "Rescue a surrounded ally"


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

# Surrounded entry-roll signal weights (#1733). Fed as perform_check extra_modifiers
# for the entry roll (Task 6) — authored content (the surrounded_entry pool's rows)
# decides the actual odds; these are inputs to that roll, not a code-level gate.
SURROUNDED_ENTRY_ISOLATED_MODIFIER = -15  # isolated: no ally at your BattlePlace
SURROUNDED_ENTRY_MOBILITY_MODIFIER = 40  # active, unimpaired MOVEMENT capability
