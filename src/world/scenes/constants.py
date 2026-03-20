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


class InteractionMode(models.TextChoices):
    """The type of IC interaction."""

    POSE = "pose", "Pose"
    EMIT = "emit", "Emit"
    SAY = "say", "Say"
    WHISPER = "whisper", "Whisper"
    SHOUT = "shout", "Shout"
    ACTION = "action", "Action"


class InteractionVisibility(models.TextChoices):
    """Per-interaction privacy override. Can only escalate, never reduce."""

    DEFAULT = "default", "Default"
    VERY_PRIVATE = "very_private", "Very Private"


class ScenePrivacyMode(models.TextChoices):
    """Scene-level privacy floor. Ephemeral is immutable after creation."""

    PUBLIC = "public", "Public"
    PRIVATE = "private", "Private"
    EPHEMERAL = "ephemeral", "Ephemeral"


class SummaryAction(models.TextChoices):
    """Actions in the collaborative ephemeral scene summary flow."""

    SUBMIT = "submit", "Submit"
    EDIT = "edit", "Edit"
    AGREE = "agree", "Agree"


class SummaryStatus(models.TextChoices):
    """Status of an ephemeral scene's collaborative summary."""

    DRAFT = "draft", "Draft"
    PENDING_REVIEW = "pending_review", "Pending Review"
    AGREED = "agreed", "Agreed"
