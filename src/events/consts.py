from django.db import models


class NotificationTiming(models.TextChoices):
    PRE_PROCESS = "PRE_PROCESS", "Pre-processing"
    POST_PROCESS = "POST_PROCESS", "Post-processing"


class EventType(models.TextChoices):
    EXAMINE = "EXAMINE", "Examine"
    ATTACK = "ATTACK", "Attack"
    MOVE = "MOVE", "Move"
    TALK = "TALK", "Talk"
    USE = "USE", "Use"
    MAGIC = "MAGIC", "Magic"
    KILL = "KILL", "Kill"
    DAMAGE = "DAMAGE", "Damage"
    # Add more event types as needed
