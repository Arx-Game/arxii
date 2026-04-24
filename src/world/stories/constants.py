from django.db import models


class EraStatus(models.TextChoices):
    UPCOMING = "upcoming", "Upcoming"
    ACTIVE = "active", "Active"
    CONCLUDED = "concluded", "Concluded"


class StoryScope(models.TextChoices):
    CHARACTER = "character", "Character"
    GROUP = "group", "Group"
    GLOBAL = "global", "Global"


class BeatPredicateType(models.TextChoices):
    GM_MARKED = "gm_marked", "GM-marked"
    CHARACTER_LEVEL_AT_LEAST = "character_level_at_least", "Character level at least"
    ACHIEVEMENT_HELD = "achievement_held", "Achievement held"
    CONDITION_HELD = "condition_held", "Condition held"
    CODEX_ENTRY_UNLOCKED = "codex_entry_unlocked", "Codex entry unlocked"
    STORY_AT_MILESTONE = "story_at_milestone", "Referenced story at milestone"
    AGGREGATE_THRESHOLD = "aggregate_threshold", "Aggregate threshold reached"


class StoryMilestoneType(models.TextChoices):
    """Which kind of milestone a STORY_AT_MILESTONE beat checks against."""

    STORY_RESOLVED = "story_resolved", "Story resolved"
    CHAPTER_REACHED = "chapter_reached", "Chapter reached or passed"
    EPISODE_REACHED = "episode_reached", "Episode reached or passed"


class AssistantClaimStatus(models.TextChoices):
    REQUESTED = "requested", "Requested"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    CANCELLED = "cancelled", "Cancelled"
    COMPLETED = "completed", "Completed"


class SessionRequestStatus(models.TextChoices):
    OPEN = "open", "Open — awaiting scheduling"
    SCHEDULED = "scheduled", "Scheduled (Event created)"
    RESOLVED = "resolved", "Resolved (session complete)"
    CANCELLED = "cancelled", "Cancelled"


class BeatOutcome(models.TextChoices):
    UNSATISFIED = "unsatisfied", "Unsatisfied"
    SUCCESS = "success", "Success"
    FAILURE = "failure", "Failure"
    EXPIRED = "expired", "Expired"
    PENDING_GM_REVIEW = "pending_gm_review", "Pending GM review"


class BeatVisibility(models.TextChoices):
    HINTED = "hinted", "Hinted"
    SECRET = "secret", "Secret"
    VISIBLE = "visible", "Visible"


class TransitionMode(models.TextChoices):
    AUTO = "auto", "Auto"
    GM_CHOICE = "gm_choice", "GM Choice"


class StoryEpisodeStatus(models.TextChoices):
    """Coarse status of a story's current episode, exposed via dashboards.

    Callers consume the status code and render their own labels / UI;
    the service does not return human-readable strings.
    """

    ON_HOLD = "on_hold", "On hold (frontier — unauthored next)"
    WAITING_ON_BEATS = "waiting_on_beats", "Waiting on progression beats"
    READY_TO_RESOLVE = "ready_to_resolve", "Ready to resolve (auto-advance possible)"
    READY_TO_SCHEDULE = "ready_to_schedule", "Ready to schedule GM session"
    SCHEDULED = "scheduled", "GM session scheduled"
