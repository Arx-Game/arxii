from django.db import models


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
    MUTTER = "mutter", "Mutter"
    SHOUT = "shout", "Shout"
    ACTION = "action", "Action"
    OUTCOME = "outcome", "Outcome"


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


class PersonaType(models.TextChoices):
    """The permanence level of a persona."""

    PRIMARY = "primary", "Primary"
    ESTABLISHED = "established", "Established"
    TEMPORARY = "temporary", "Temporary"
    ALTERNATE = "alternate", "Alternate"


class PlaceStatus(models.TextChoices):
    """Status of a Place within a room."""

    ACTIVE = "active", "Active"
    REMOVED = "removed", "Removed"
    HIDDEN = "hidden", "Hidden"


class PoseKind(models.TextChoices):
    """Classifies an Interaction pose for scene-entry endorsement filtering (Spec C)."""

    STANDARD = "standard", "Standard"
    ENTRY = "entry", "Entry"
    DEPARTURE = "departure", "Departure"  # reserved — future departure mechanic


class ReactionWindowKind(models.TextChoices):
    """Kinds of reaction windows on scene events (#904).

    Each kind registers a ReactionKindConfig (choices provider + handlers)
    via world.scenes.reaction_services.register_reaction_kind — usually from
    the owning app's AppConfig.ready(). Future consumers (spread-assist,
    fashion) add values here with their handlers.
    """

    ENTRANCE = "entrance", "Make an Entrance"
    KUDOS = "kudos", "Kudos"
    SPREAD_ASSIST = "spread_assist", "Acclaim the Telling"  # PLACEHOLDER label


class RoundStatus(models.TextChoices):
    """Lifecycle status of a scene or combat encounter round."""

    DECLARING = "declaring", "Declaring"
    RESOLVING = "resolving", "Resolving"
    BETWEEN_ROUNDS = "between_rounds", "Between Rounds"
    COMPLETED = "completed", "Completed"


class SceneRoundParticipantStatus(models.TextChoices):
    """Whether a character is currently taking turns in a scene round."""

    ACTIVE = "active", "Active"
    LEFT = "left", "Left"


# Scene-round statuses that represent an ongoing (non-completed) round.
ACTIVE_SCENE_ROUND_STATUSES = frozenset(
    {RoundStatus.DECLARING, RoundStatus.RESOLVING, RoundStatus.BETWEEN_ROUNDS}
)


class SceneRoundStartReason(models.TextChoices):
    OPT_IN = "opt_in", "Player opt-in"
    GM = "gm", "GM-started"
    DANGER = "danger", "Danger (auto-started)"


class SceneRoundMode(models.TextChoices):
    """How a scene round gates player actions (orthogonal to start_reason)."""

    OPEN = "open", "Open (immediate, unbounded)"
    POSE_ORDER = "pose_order", "Pose order (immediate, quota-gated)"
    STRICT = "strict", "Strict (declare, batch-resolved)"


class ReactionValence(models.IntegerChoices):
    """Relationship effect of a catalog reaction emoji (#1699).

    NEUTRAL emoji are cosmetic only (today's behavior); nonzero valence
    additionally fires an ambient relationship bump at the pose's author.
    """

    POSITIVE = 1, "Positive"
    NEUTRAL = 0, "Neutral"
    NEGATIVE = -1, "Negative"


class DecisiveCheckMarkerStatus(models.TextChoices):
    """Lifecycle status of a DecisiveCheckMarker (#1748)."""

    PENDING = "pending", "Pending"
    RESOLVED = "resolved", "Resolved"
    CANCELLED = "cancelled", "Cancelled"
