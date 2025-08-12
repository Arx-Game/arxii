from dataclasses import dataclass
from typing import List, Optional

from django.db import models


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
    consequences: List[str]
    next_episode_setup: Optional[str]
