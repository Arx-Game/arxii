from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Union

from django.db import models

if TYPE_CHECKING:
    from world.stories.models import (
        Beat,
        BeatCompletion,
        EpisodeResolution,
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


@dataclass
class StoryLogBeatEntry:
    """One beat-completion entry in a story log.

    Carries the Beat and its BeatCompletion model instances directly so
    consumers can walk FKs as needed. The visibility-filtered text fields
    are pre-computed by serialize_story_log based on the viewer role:
    - Player viewer: visible_internal_description is None;
      visible_player_hint is empty for SECRET beats (still active)
      but visible_player_resolution_text is populated on completion.
    - Lead GM / Staff: all fields populated from the underlying models.
    """

    beat: Beat
    completion: BeatCompletion

    # Pre-filtered text the serializer will surface. These are NOT
    # denormalized copies of model fields — they are the post-filtering
    # view tailored to the requester's role.
    visible_player_hint: str
    visible_player_resolution_text: str
    visible_internal_description: str | None  # None hides it for player viewers
    visible_gm_notes: str | None  # None hides it for player viewers


@dataclass
class StoryLogEpisodeEntry:
    """One episode-resolution entry in a story log.

    Carries the EpisodeResolution model instance directly; consumers walk
    FKs (resolution.episode, resolution.chosen_transition, etc.) rather
    than reading denormalized copies from this dataclass.
    """

    resolution: EpisodeResolution

    # Pre-filtered field: GM notes hidden from player viewers
    visible_internal_notes: str | None
