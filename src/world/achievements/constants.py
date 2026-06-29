from django.db import models


class NotificationLevel(models.TextChoices):
    PERSONAL = "personal", "Personal"
    ROOM = "room", "Room"
    GAMEWIDE = "gamewide", "Gamewide"


class ComparisonType(models.TextChoices):
    GTE = "gte", "Greater than or equal"
    EQ = "eq", "Equal to"
    LTE = "lte", "Less than or equal"


class RewardType(models.TextChoices):
    TITLE = "title", "Title"
    BONUS = "bonus", "Mechanical Bonus"
    COSMETIC = "cosmetic", "Cosmetic"
    PRESTIGE = "prestige", "Prestige"


class ConditionEventType(models.TextChoices):
    """Event types from world.conditions that can trigger StatDefinition increments.

    Used by ConditionStatRule (see world.achievements.models) to route
    per-condition events to stat increments. Slice-1 ships only GAINED;
    future event types (REMOVED, STAGE_ADVANCED, SEVERITY_REACHED) add
    one entry each without schema changes.
    """

    GAINED = "gained", "Condition gained"


class AccessChangeSource(models.TextChoices):
    """Sources of ability access changes for use in granted-ability messages.

    Lead-in message text for notifications when a character's access to
    abilities changes (e.g., gaining or losing techniques).
    """

    ASSUMED_ALTERNATE_SELF = "assumed_alternate_self", "assuming an alternate self"
    REVERTED_ALTERNATE_SELF = "reverted_alternate_self", "reverting to your true self"
    COVENANT_ROLE_ENGAGED = "covenant_role_engaged", "taking up your covenant role"
    COVENANT_ROLE_DISENGAGED = "covenant_role_disengaged", "setting down your covenant role"
    CHARACTER_CREATION = "character_creation", "your origins"
