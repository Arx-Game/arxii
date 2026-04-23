"""Assistant GM claim lifecycle services.

Flow:
    request_claim -> approve_claim / reject_claim / cancel_claim
    approved -> complete_claim (after session runs)

All state transitions validate current state and permissions. Raises
typed AssistantClaimError subclasses so API views can surface
user_message safely.
"""

from __future__ import annotations

from django.db import transaction

from world.gm.models import GMProfile
from world.stories.constants import AssistantClaimStatus
from world.stories.exceptions import (
    BeatNotAGMEligibleError,
    ClaimApprovalPermissionError,
    ClaimStateTransitionError,
)
from world.stories.models import AssistantGMClaim, Beat


def request_claim(
    *,
    beat: Beat,
    assistant_gm: GMProfile,
    framing_note: str = "",
) -> AssistantGMClaim:
    """AGM requests to run this beat. Beat must be flagged agm_eligible."""
    if not beat.agm_eligible:
        raise BeatNotAGMEligibleError
    return AssistantGMClaim.objects.create(
        beat=beat,
        assistant_gm=assistant_gm,
        framing_note=framing_note,
        status=AssistantClaimStatus.REQUESTED,
    )


def approve_claim(
    *,
    claim: AssistantGMClaim,
    approver: GMProfile,
    framing_note: str | None = None,
) -> AssistantGMClaim:
    """Lead GM or Staff approves the claim.

    If framing_note is provided, update the claim's framing_note (Lead GM
    authors the framing here, AFTER the AGM has requested).
    """
    if claim.status != AssistantClaimStatus.REQUESTED:
        raise ClaimStateTransitionError
    if not _can_approve(claim=claim, approver=approver):
        raise ClaimApprovalPermissionError
    update_fields = ["status", "approved_by", "updated_at"]
    if framing_note is not None:
        update_fields.append("framing_note")
    with transaction.atomic():
        claim.status = AssistantClaimStatus.APPROVED
        claim.approved_by = approver
        if framing_note is not None:
            claim.framing_note = framing_note
        claim.save(update_fields=update_fields)
    return claim


def reject_claim(
    *,
    claim: AssistantGMClaim,
    approver: GMProfile,
    note: str = "",
) -> AssistantGMClaim:
    """Reject the claim with an optional note."""
    if claim.status != AssistantClaimStatus.REQUESTED:
        raise ClaimStateTransitionError
    if not _can_approve(claim=claim, approver=approver):
        raise ClaimApprovalPermissionError
    with transaction.atomic():
        claim.status = AssistantClaimStatus.REJECTED
        claim.approved_by = approver
        claim.rejection_note = note
        claim.save(update_fields=["status", "approved_by", "rejection_note", "updated_at"])
    return claim


def cancel_claim(*, claim: AssistantGMClaim) -> AssistantGMClaim:
    """The requesting AGM cancels their own claim before approval.

    Only allowed while status is REQUESTED. Once APPROVED, the Lead GM
    completes or rejects via different paths.
    """
    if claim.status != AssistantClaimStatus.REQUESTED:
        raise ClaimStateTransitionError
    claim.status = AssistantClaimStatus.CANCELLED
    claim.save(update_fields=["status", "updated_at"])
    return claim


def complete_claim(
    *,
    claim: AssistantGMClaim,
    completer: GMProfile,
) -> AssistantGMClaim:
    """Mark an approved claim COMPLETED after the session has run.

    Typically called by the Lead GM after reviewing the AGM's session.
    """
    if claim.status != AssistantClaimStatus.APPROVED:
        raise ClaimStateTransitionError
    if not _can_approve(claim=claim, approver=completer):
        raise ClaimApprovalPermissionError
    claim.status = AssistantClaimStatus.COMPLETED
    claim.save(update_fields=["status", "updated_at"])
    return claim


def _can_approve(*, claim: AssistantGMClaim, approver: GMProfile) -> bool:
    """Return True if approver is the Lead GM of the story's primary table OR is staff.

    The Lead GM is identified as the GMTable.gm of the story's primary_table.
    Staff is identified by approver.account.is_staff.
    """
    # Staff override
    try:
        if approver.account.is_staff:
            return True
    except AttributeError:
        pass
    # Lead GM check — the story's primary_table.gm is the Lead GM
    story = claim.beat.episode.chapter.story
    primary_table = story.primary_table
    if primary_table is None:
        return False
    return primary_table.gm_id == approver.pk
