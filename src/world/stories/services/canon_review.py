"""Canon-impact review service layer (#2003).

All ``CanonReview`` lifecycle transitions live here. The readiness gate itself
is in :mod:`world.stories.services.stakes` (``validate_stakes_readiness``) —
this module answers "is this story cleared?" and mutates review rows.

Auto-downgrade, never hard-block: an unreviewed WORLD-tier story's staked beats
activate UNREADY (effective risk NONE); the scene still runs and nothing pays.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from world.stories.constants import CanonReviewStatus
from world.stories.models import Beat, CanonReview, Story

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.gm.models import GMProfile


def latest_review_for_story(story: Story) -> CanonReview | None:
    """The most recent ``CanonReview`` for ``story`` (any status), or None."""
    return story.canon_reviews.order_by("-created_at").first()


def pending_canon_reviews() -> QuerySet[CanonReview]:
    """All PENDING canon reviews, oldest first (for the staff queue)."""
    return (
        CanonReview.objects.filter(status=CanonReviewStatus.PENDING)
        .select_related("story")
        .order_by("created_at")
    )


def story_is_cleared(story: Story) -> bool:
    """True iff ``story`` has at least one CLEARED review."""
    return story.canon_reviews.filter(status=CanonReviewStatus.CLEARED).exists()


def escalation_tier_for_story(story: Story) -> str:
    """The effective impact tier after the beat-level escalation heuristic (#2003).

    Authored data only (never parsed from prose). On a GROUP/GLOBAL story, any
    beat staking a society-level FACTION subject, or carrying EXTREME declared
    risk, escalates the effective tier to at least REGIONAL for review purposes.
    TABLE/CHARACTER-scope stories never escalate. The result is surfaced as a
    readiness problem (not a hard block) by callers — the author's
    ``impact_tier`` is unchanged on the model.

    Returns an ``ImpactTier`` value.
    """
    from world.societies.constants import RenownRisk  # noqa: PLC0415
    from world.stories.constants import (  # noqa: PLC0415
        ImpactTier,
        StakeSubjectKind,
        StoryScope,
    )

    if story.scope not in (StoryScope.GROUP, StoryScope.GLOBAL):
        return story.impact_tier
    if story.impact_tier == ImpactTier.WORLD:
        # Already the highest — no further escalation possible.
        return ImpactTier.WORLD

    story_beats = Beat.objects.filter(episode__chapter__story=story)
    escalates = story_beats.filter(
        stakes__subject_kind=StakeSubjectKind.FACTION,
        stakes__subject_society__isnull=False,
    ).exists()
    if not escalates:
        escalates = story_beats.filter(risk=RenownRisk.EXTREME).exists()

    if escalates:
        return ImpactTier.REGIONAL
    return story.impact_tier


def regional_auto_clears(gm_profile: GMProfile) -> bool:
    """Whether ``gm_profile``'s level cap auto-clears REGIONAL impact tiers."""
    from world.gm.models import GMLevelCap  # noqa: PLC0415

    cap = GMLevelCap.objects.filter(level=gm_profile.level).first()
    return bool(cap and cap.auto_clear_regional)


def request_canon_review(story: Story) -> CanonReview:
    """Create a PENDING ``CanonReview`` for ``story``.

    Idempotent: returns the existing pending review if one is already open.
    """
    existing = story.canon_reviews.filter(status=CanonReviewStatus.PENDING).first()
    if existing is not None:
        return existing
    with transaction.atomic():
        review, _created = CanonReview.objects.get_or_create(
            story=story,
            status=CanonReviewStatus.PENDING,
            defaults={"tier": story.impact_tier},
        )
    return review


def clear_canon_review(
    review: CanonReview,
    reviewer: AccountDB,
    *,
    notes: str = "",
) -> CanonReview:
    """Mark a PENDING review CLEARED and stamp the resolution."""
    if review.status != CanonReviewStatus.PENDING:
        msg = (
            f"CanonReview {review.pk} is not PENDING (status={review.status!r}); "
            "only PENDING reviews can be cleared."
        )
        raise ValueError(msg)
    review.status = CanonReviewStatus.CLEARED
    review.reviewer = reviewer
    review.notes = notes
    review.resolved_at = timezone.now()
    review.save(update_fields=["status", "reviewer", "notes", "resolved_at"])
    return review


def request_changes(
    review: CanonReview,
    reviewer: AccountDB,
    *,
    notes: str,
) -> CanonReview:
    """Send a PENDING review back to the Lead GM with change-request notes."""
    if review.status != CanonReviewStatus.PENDING:
        msg = (
            f"CanonReview {review.pk} is not PENDING (status={review.status!r}); "
            "only PENDING reviews can be returned with changes requested."
        )
        raise ValueError(msg)
    review.status = CanonReviewStatus.CHANGES_REQUESTED
    review.reviewer = reviewer
    review.notes = notes
    review.resolved_at = timezone.now()
    review.save(update_fields=["status", "reviewer", "notes", "resolved_at"])
    return review
