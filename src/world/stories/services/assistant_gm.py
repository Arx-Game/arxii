"""Assistant GM claim lifecycle services.

Flow:
    request_claim -> approve_claim / reject_claim / cancel_claim
    approved -> complete_claim (after session runs)

State and permission validation is now handled by input serializers and permission
classes in the view layer. Services contain only defensive programmer-error guards.
"""

from __future__ import annotations

from django.db import transaction

from world.gm.models import GMProfile
from world.stories.constants import AssistantClaimStatus
from world.stories.models import AssistantGMClaim, Beat


def request_claim(
    *,
    beat: Beat,
    assistant_gm: GMProfile,
    framing_note: str = "",
) -> AssistantGMClaim:
    """AGM requests to run this beat.

    Defensive guard: RequestClaimInputSerializer validates agm_eligible for API callers.
    If called directly with an ineligible beat, raises ValueError.
    """
    if not beat.agm_eligible:
        msg = (
            f"Beat {beat.pk} is not flagged as agm_eligible; "
            "RequestClaimInputSerializer should have rejected this."
        )
        raise ValueError(msg)
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
    """Lead GM approves the claim.

    If framing_note is provided, update the claim's framing_note (Lead GM
    authors the framing here, AFTER the AGM has requested).

    Defensive guards: ApproveClaimInputSerializer validates status for API callers.
    Permission is enforced by IsLeadGMOnClaimStoryOrStaff + IsGMProfile.
    Race condition: if claim status changes between serializer validation and this call,
    the guard fires — acceptable for an infrequent edge case.
    """
    if claim.status != AssistantClaimStatus.REQUESTED:
        msg = (
            f"Claim {claim.pk} is not REQUESTED (status={claim.status!r}); "
            "ApproveClaimInputSerializer should have rejected this."
        )
        raise ValueError(msg)
    if not _can_approve(claim=claim, approver=approver):
        msg = f"Approver {approver.pk} is not authorized to approve claim {claim.pk}."
        raise ValueError(msg)
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
    """Reject the claim with an optional note.

    Defensive guards: RejectClaimInputSerializer validates status for API callers.
    Race condition: if claim status changes between serializer validation and this call,
    the guard fires — acceptable for an infrequent edge case.
    """
    if claim.status != AssistantClaimStatus.REQUESTED:
        msg = (
            f"Claim {claim.pk} is not REQUESTED (status={claim.status!r}); "
            "RejectClaimInputSerializer should have rejected this."
        )
        raise ValueError(msg)
    if not _can_approve(claim=claim, approver=approver):
        msg = f"Approver {approver.pk} is not authorized to reject claim {claim.pk}."
        raise ValueError(msg)
    with transaction.atomic():
        claim.status = AssistantClaimStatus.REJECTED
        claim.approved_by = approver
        claim.rejection_note = note
        claim.save(update_fields=["status", "approved_by", "rejection_note", "updated_at"])
    return claim


def cancel_claim(*, claim: AssistantGMClaim) -> AssistantGMClaim:
    """The requesting AGM cancels their own claim before approval.

    Defensive guard: CancelClaimInputSerializer validates status for API callers.
    Race condition: if claim status changes between serializer validation and this call,
    the guard fires — acceptable for an infrequent edge case.
    """
    if claim.status != AssistantClaimStatus.REQUESTED:
        msg = (
            f"Claim {claim.pk} is not REQUESTED (status={claim.status!r}); "
            "CancelClaimInputSerializer should have rejected this."
        )
        raise ValueError(msg)
    claim.status = AssistantClaimStatus.CANCELLED
    claim.save(update_fields=["status", "updated_at"])
    return claim


def complete_claim(
    *,
    claim: AssistantGMClaim,
    completer: GMProfile,
) -> AssistantGMClaim:
    """Mark an approved claim COMPLETED after the session has run.

    Defensive guards: CompleteClaimInputSerializer validates status for API callers.
    Race condition: if claim status changes between serializer validation and this call,
    the guard fires — acceptable for an infrequent edge case.
    """
    if claim.status != AssistantClaimStatus.APPROVED:
        msg = (
            f"Claim {claim.pk} is not APPROVED (status={claim.status!r}); "
            "CompleteClaimInputSerializer should have rejected this."
        )
        raise ValueError(msg)
    if not _can_approve(claim=claim, approver=completer):
        msg = f"Completer {completer.pk} is not authorized to complete claim {claim.pk}."
        raise ValueError(msg)
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
