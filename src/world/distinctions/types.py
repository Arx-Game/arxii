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


def build_distinction_entry(
    distinction: Distinction, rank: int, notes: str = ""
) -> DraftDistinctionEntry:
    """Build the dictionary entry for a distinction on a draft."""
    return DraftDistinctionEntry(
        distinction_id=distinction.id,
        distinction_name=distinction.name,
        distinction_slug=distinction.slug,
        category_slug=distinction.category.slug,
        rank=rank,
        cost=distinction.calculate_total_cost(rank),
        notes=notes,
    )


class DistinctionOrigin(models.TextChoices):
    """How a character acquired a distinction.

    ``GAMEPLAY`` is vestigial (#2037) — kept for schema stability, but no
    production writer assigns it. The four values below are the ratified
    post-CG acquisition sources; every in-play grant goes through
    ``world.distinctions.services.grant_distinction`` and stamps one of them.
    """

    CHARACTER_CREATION = "character_creation", "Character Creation"
    GAMEPLAY = "gameplay", "Gameplay"
    GM_AWARD = "gm_award", "GM Award"
    ACHIEVEMENT_AUTO_GRANT = "achievement_auto_grant", "Achievement"
    CONSEQUENCE_POOL = "consequence_pool", "Consequence"
    ENDORSEMENT_THRESHOLD = "endorsement_threshold", "Endorsement Threshold"


class OtherStatus(models.TextChoices):
    """Status of a freeform 'Other' distinction entry."""

    PENDING_REVIEW = "pending_review", "Pending Review"
    APPROVED = "approved", "Approved"
    MAPPED = "mapped", "Mapped to Distinction"
