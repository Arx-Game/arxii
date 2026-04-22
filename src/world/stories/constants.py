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
