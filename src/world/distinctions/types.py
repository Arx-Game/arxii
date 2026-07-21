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

    ``GAMEPLAY`` was vestigial from #2037 through #2441 — kept for schema
    stability, no production writer assigned it. #2441 Task 8 became its first
    production writer: ``world.magic.services.tradition_membership.
    leave_tradition`` stamps it when re-applying the Unbound drawback, an
    automatic system consequence of the player's own leave-tradition action that
    doesn't fit any of the other four sources (no GM, achievement, consequence
    pool, or endorsement threshold involved). Every in-play grant goes through
    ``world.distinctions.services.grant_distinction`` and stamps one of these
    six values.

    ``SPECIES`` (#2472) is a finalize-time origin alongside ``CHARACTER_CREATION``:
    it marks a distinction forced onto the sheet by the character's species
    (e.g. a minor gift auto-granted to fill an empty gift slot) rather than one
    the player spent points on during the draft.
    """

    CHARACTER_CREATION = "character_creation", "Character Creation"
    GAMEPLAY = "gameplay", "Gameplay"
    GM_AWARD = "gm_award", "GM Award"
    ACHIEVEMENT_AUTO_GRANT = "achievement_auto_grant", "Achievement"
    CONSEQUENCE_POOL = "consequence_pool", "Consequence"
    ENDORSEMENT_THRESHOLD = "endorsement_threshold", "Endorsement Threshold"
    SPECIES = "species", "Species"


class OtherStatus(models.TextChoices):
    """Status of a freeform 'Other' distinction entry."""

    PENDING_REVIEW = "pending_review", "Pending Review"
    APPROVED = "approved", "Approved"
    MAPPED = "mapped", "Mapped to Distinction"


#: Flat XP charged per CG point when adding/removing a distinction via a GM
#: table request (#2607). Applied only on the benefit direction (gain positive
#: or shed negative); free otherwise. No per-distinction override in v1.
DISTINCTION_CHANGE_XP_PER_CG_POINT = 3
