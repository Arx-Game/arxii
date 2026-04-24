from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Union

from django.db import models

if TYPE_CHECKING:
    from world.stories.models import (
        GlobalStoryProgress,
        GroupStoryProgress,
        StoryProgress,
    )

AnyStoryProgress = Union["StoryProgress", "GroupStoryProgress", "GlobalStoryProgress"]


class StoryStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class StoryPrivacy(models.TextChoices):
    PUBLIC = "public", "Public"
    PRIVATE = "private", "Private"
    INVITE_ONLY = "invite_only", "Invite Only"


class ParticipationLevel(models.TextChoices):
    CRITICAL = (
        "critical",
        "Critical",
    )  # Character's participation is essential to the story
    IMPORTANT = (
        "important",
        "Important",
    )  # Character has significant role but story can continue without them
    OPTIONAL = "optional", "Optional"  # Character can drop in/out without major impact


class TrustLevel(models.IntegerChoices):
    UNTRUSTED = 0, "Untrusted"
    BASIC = 1, "Basic"
    INTERMEDIATE = 2, "Intermediate"
    ADVANCED = 3, "Advanced"
    EXPERT = 4, "Expert"


# ContentElement removed - trust categories are now dynamic database entities
# See TrustCategory model in models.py


class ConnectionType(models.TextChoices):
    THEREFORE = "therefore", "Therefore"
    BUT = "but", "But"


@dataclass
class StoryStatusSummary:
    """Structured status of a story's current episode, for dashboard consumption.

    Callers render their own presentation (player dashboard, GM queue,
    staff workload) from this structure — the service does not return
    rendered strings.
    """

    status: str  # StoryEpisodeStatus value
    chapter_order: int | None
    chapter_title: str | None
    episode_order: int | None
    episode_title: str | None
    open_session_request_id: int | None
    scheduled_event_id: int | None
    scheduled_real_time: datetime | None


@dataclass
class SceneConnection:
    """Represents how one scene connects to another using 'but'/'therefore' logic"""

    from_scene_id: int
    to_scene_id: int
    connection_type: str  # 'therefore' or 'but'
    summary: str  # Brief explanation of how they connect


@dataclass
class EpisodeSummary:
    """Summary of an episode's narrative beats and consequences"""

    episode_id: int
    summary: str
    consequences: list[str]
    next_episode_setup: str | None


# Entry type constants for story log entries.
LOG_ENTRY_BEAT_COMPLETION = "beat_completion"
LOG_ENTRY_EPISODE_RESOLUTION = "episode_resolution"


@dataclass
class StoryLogBeatEntry:
    """One beat-completion entry in a story log.

    Fields are pre-filtered for the requester's viewer role:
    - Player: internal_description is None; player_hint / player_resolution_text
      reflect the beat's visibility rules.
    - Lead GM / Staff: internal_description populated; all fields visible.
    """

    entry_type: str  # "beat_completion"
    beat_id: int
    episode_id: int
    recorded_at: datetime
    outcome: str
    visibility: str  # passthrough for frontend rendering
    player_hint: str
    player_resolution_text: str
    internal_description: str | None  # None for player viewers
    gm_notes: str | None  # None for player viewers


@dataclass
class StoryLogEpisodeEntry:
    """One episode-resolution entry in a story log."""

    entry_type: str  # "episode_resolution"
    episode_id: int
    episode_title: str
    resolved_at: datetime
    transition_id: int | None
    target_episode_id: int | None
    target_episode_title: str | None
    connection_type: str  # "therefore", "but", or empty
    connection_summary: str
    internal_notes: str | None  # Lead GM / staff only
