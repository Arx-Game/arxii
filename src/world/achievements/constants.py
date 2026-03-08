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
