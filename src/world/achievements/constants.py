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


class ConditionEventType(models.TextChoices):
    """Event types from world.conditions that can trigger StatDefinition increments.

    Used by ConditionStatRule (see world.achievements.models) to route
    per-condition events to stat increments. Slice-1 ships only GAINED;
    future event types (REMOVED, STAGE_ADVANCED, SEVERITY_REACHED) add
    one entry each without schema changes.
    """

    GAINED = "gained", "Condition gained"
