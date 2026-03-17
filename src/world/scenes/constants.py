from django.db import models


class MessageContext(models.TextChoices):
    PUBLIC = "public", "Public"
    TABLETALK = "tabletalk", "Tabletalk"
    PRIVATE = "private", "Private"


class MessageMode(models.TextChoices):
    POSE = "pose", "Pose"
    EMIT = "emit", "Emit"
    SAY = "say", "Say"
    WHISPER = "whisper", "Whisper"
    OOC = "ooc", "OOC"


class SceneStatus(models.TextChoices):
    """Filter-level status values derived from Scene's is_active and date_finished fields."""

    ACTIVE = "active", "Active"
    COMPLETED = "completed", "Completed"
    UPCOMING = "upcoming", "Upcoming"


class SceneAction(models.TextChoices):
    """Action types for scene broadcast messages."""

    START = "start", "Start"
    UPDATE = "update", "Update"
    END = "end", "End"
