# src/world/distinctions/types.py
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypedDict

from django.db import models

if TYPE_CHECKING:
    from world.distinctions.models import Distinction


@dataclass
class ValidatedDistinction:
    """Validated distinction data for adding to a draft."""

    distinction: Distinction
    rank: int
    notes: str


class DraftDistinctionEntry(TypedDict):
    """Type for a distinction entry stored in draft_data."""

    distinction_id: int
    distinction_name: str
    distinction_slug: str
    category_slug: str
    rank: int
    cost: int
    notes: str


class EffectType(models.TextChoices):
    """Types of mechanical effects a distinction can have."""

    STAT_MODIFIER = "stat_modifier", "Stat Modifier"
    AFFINITY_MODIFIER = "affinity_modifier", "Affinity Modifier"
    RESONANCE_MODIFIER = "resonance_modifier", "Resonance Modifier"
    ROLL_MODIFIER = "roll_modifier", "Roll Modifier"
    GOAL_MODIFIER = "goal_modifier", "Goal Modifier"
    CODE_HANDLED = "code_handled", "Code Handled"


class DistinctionOrigin(models.TextChoices):
    """How a character acquired a distinction."""

    CHARACTER_CREATION = "character_creation", "Character Creation"
    GAMEPLAY = "gameplay", "Gameplay"


class OtherStatus(models.TextChoices):
    """Status of a freeform 'Other' distinction entry."""

    PENDING_REVIEW = "pending_review", "Pending Review"
    APPROVED = "approved", "Approved"
    MAPPED = "mapped", "Mapped to Distinction"
