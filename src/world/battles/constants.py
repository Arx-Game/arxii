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
BATTLE_CHECK_TYPE_NAME = "Battle Action"
