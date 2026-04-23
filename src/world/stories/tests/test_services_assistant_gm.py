"""Tests for AssistantGMClaim service functions."""

from django.db import IntegrityError
from django.test import TestCase, TransactionTestCase

from world.gm.factories import GMProfileFactory, GMTableFactory
from world.stories.constants import AssistantClaimStatus
from world.stories.exceptions import (
    BeatNotAGMEligibleError,
    ClaimApprovalPermissionError,
    ClaimStateTransitionError,
)
from world.stories.factories import AssistantGMClaimFactory, BeatFactory, StoryFactory
from world.stories.models import AssistantGMClaim
from world.stories.services.assistant_gm import (
    approve_claim,
    cancel_claim,
    complete_claim,
    reject_claim,
    request_claim,
)


def _make_lead_gm_claim(agm: object | None = None) -> tuple:
    """Return (claim, lead_gm_profile, story) with a properly wired primary_table."""
    lead_gm = GMProfileFactory()
    table = GMTableFactory(gm=lead_gm)
    story = StoryFactory(primary_table=table)
    # Build beat chain: story -> chapter -> episode -> beat
    from world.stories.factories import ChapterFactory, EpisodeFactory

    chapter = ChapterFactory(story=story)
    episode = EpisodeFactory(chapter=chapter)
    beat = BeatFactory(episode=episode, agm_eligible=True)
    agm_profile = agm if agm is not None else GMProfileFactory()
    claim = AssistantGMClaim.objects.create(
        beat=beat,
        assistant_gm=agm_profile,
        status=AssistantClaimStatus.REQUESTED,
    )
    return claim, lead_gm, story


class RequestClaimTests(TestCase):
    """Tests for request_claim()."""

    def test_happy_path_creates_requested_claim(self) -> None:
        beat = BeatFactory(agm_eligible=True)
        agm = GMProfileFactory()
        claim = request_claim(beat=beat, assistant_gm=agm)
        self.assertEqual(claim.status, AssistantClaimStatus.REQUESTED)
        self.assertEqual(claim.beat_id, beat.pk)
        self.assertEqual(claim.assistant_gm_id, agm.pk)

    def test_framing_note_stored(self) -> None:
        beat = BeatFactory(agm_eligible=True)
        agm = GMProfileFactory()
        claim = request_claim(beat=beat, assistant_gm=agm, framing_note="The scene opens on...")
        self.assertEqual(claim.framing_note, "The scene opens on...")

    def test_beat_not_eligible_raises(self) -> None:
        beat = BeatFactory(agm_eligible=False)
        agm = GMProfileFactory()
        with self.assertRaises(BeatNotAGMEligibleError):
            request_claim(beat=beat, assistant_gm=agm)

    def test_claim_persisted_to_db(self) -> None:
        beat = BeatFactory(agm_eligible=True)
        agm = GMProfileFactory()
        claim = request_claim(beat=beat, assistant_gm=agm)
        reloaded = AssistantGMClaim.objects.get(pk=claim.pk)
        self.assertEqual(reloaded.status, AssistantClaimStatus.REQUESTED)


class RequestClaimUniqueConstraintTests(TransactionTestCase):
    """Unique constraint tests for request_claim."""

    def test_duplicate_requested_claim_raises_integrity_error(self) -> None:
        beat = BeatFactory(agm_eligible=True)
        agm = GMProfileFactory()
        request_claim(beat=beat, assistant_gm=agm)
        with self.assertRaises(IntegrityError):
            request_claim(beat=beat, assistant_gm=agm)


class ApproveClaimTests(TestCase):
    """Tests for approve_claim()."""

    def test_happy_path_lead_gm_approves(self) -> None:
        claim, lead_gm, _ = _make_lead_gm_claim()
        result = approve_claim(claim=claim, approver=lead_gm)
        self.assertEqual(result.status, AssistantClaimStatus.APPROVED)
        self.assertEqual(result.approved_by_id, lead_gm.pk)

    def test_approved_claim_persisted_to_db(self) -> None:
        claim, lead_gm, _ = _make_lead_gm_claim()
        approve_claim(claim=claim, approver=lead_gm)
        claim.refresh_from_db()
        self.assertEqual(claim.status, AssistantClaimStatus.APPROVED)

    def test_framing_note_updated_on_approve(self) -> None:
        claim, lead_gm, _ = _make_lead_gm_claim()
        approve_claim(claim=claim, approver=lead_gm, framing_note="It was a dark night...")
        claim.refresh_from_db()
        self.assertEqual(claim.framing_note, "It was a dark night...")

    def test_framing_note_not_cleared_when_none_passed(self) -> None:
        claim, lead_gm, _ = _make_lead_gm_claim()
        claim.framing_note = "Existing note"
        claim.save(update_fields=["framing_note"])
        approve_claim(claim=claim, approver=lead_gm, framing_note=None)
        claim.refresh_from_db()
        self.assertEqual(claim.framing_note, "Existing note")

    def test_state_transition_error_when_already_approved(self) -> None:
        claim, lead_gm, _ = _make_lead_gm_claim()
        claim.status = AssistantClaimStatus.APPROVED
        claim.save(update_fields=["status"])
        with self.assertRaises(ClaimStateTransitionError):
            approve_claim(claim=claim, approver=lead_gm)

    def test_state_transition_error_when_rejected(self) -> None:
        claim, lead_gm, _ = _make_lead_gm_claim()
        claim.status = AssistantClaimStatus.REJECTED
        claim.save(update_fields=["status"])
        with self.assertRaises(ClaimStateTransitionError):
            approve_claim(claim=claim, approver=lead_gm)

    def test_state_transition_error_when_cancelled(self) -> None:
        claim, lead_gm, _ = _make_lead_gm_claim()
        claim.status = AssistantClaimStatus.CANCELLED
        claim.save(update_fields=["status"])
        with self.assertRaises(ClaimStateTransitionError):
            approve_claim(claim=claim, approver=lead_gm)

    def test_permission_error_for_non_lead_gm(self) -> None:
        claim, _, _ = _make_lead_gm_claim()
        outsider = GMProfileFactory()
        with self.assertRaises(ClaimApprovalPermissionError):
            approve_claim(claim=claim, approver=outsider)

    def test_staff_account_can_approve(self) -> None:
        claim, _, _ = _make_lead_gm_claim()
        staff_gm = GMProfileFactory()
        staff_gm.account.is_staff = True
        staff_gm.account.save()
        result = approve_claim(claim=claim, approver=staff_gm)
        self.assertEqual(result.status, AssistantClaimStatus.APPROVED)


class RejectClaimTests(TestCase):
    """Tests for reject_claim()."""

    def test_happy_path_lead_gm_rejects(self) -> None:
        claim, lead_gm, _ = _make_lead_gm_claim()
        result = reject_claim(claim=claim, approver=lead_gm, note="Not suitable.")
        self.assertEqual(result.status, AssistantClaimStatus.REJECTED)
        self.assertEqual(result.rejection_note, "Not suitable.")
        self.assertEqual(result.approved_by_id, lead_gm.pk)

    def test_rejection_persisted_to_db(self) -> None:
        claim, lead_gm, _ = _make_lead_gm_claim()
        reject_claim(claim=claim, approver=lead_gm, note="Reason.")
        claim.refresh_from_db()
        self.assertEqual(claim.status, AssistantClaimStatus.REJECTED)
        self.assertEqual(claim.rejection_note, "Reason.")

    def test_state_transition_error_when_not_requested(self) -> None:
        claim, lead_gm, _ = _make_lead_gm_claim()
        claim.status = AssistantClaimStatus.APPROVED
        claim.save(update_fields=["status"])
        with self.assertRaises(ClaimStateTransitionError):
            reject_claim(claim=claim, approver=lead_gm)

    def test_permission_error_for_non_lead_gm(self) -> None:
        claim, _, _ = _make_lead_gm_claim()
        outsider = GMProfileFactory()
        with self.assertRaises(ClaimApprovalPermissionError):
            reject_claim(claim=claim, approver=outsider)

    def test_staff_account_can_reject(self) -> None:
        claim, _, _ = _make_lead_gm_claim()
        staff_gm = GMProfileFactory()
        staff_gm.account.is_staff = True
        staff_gm.account.save()
        result = reject_claim(claim=claim, approver=staff_gm, note="Staff rejected.")
        self.assertEqual(result.status, AssistantClaimStatus.REJECTED)


class CancelClaimTests(TestCase):
    """Tests for cancel_claim()."""

    def test_happy_path_agm_cancels_requested_claim(self) -> None:
        claim = AssistantGMClaimFactory(status=AssistantClaimStatus.REQUESTED)
        result = cancel_claim(claim=claim)
        self.assertEqual(result.status, AssistantClaimStatus.CANCELLED)

    def test_cancellation_persisted_to_db(self) -> None:
        claim = AssistantGMClaimFactory(status=AssistantClaimStatus.REQUESTED)
        cancel_claim(claim=claim)
        claim.refresh_from_db()
        self.assertEqual(claim.status, AssistantClaimStatus.CANCELLED)

    def test_state_transition_error_when_already_approved(self) -> None:
        claim = AssistantGMClaimFactory(status=AssistantClaimStatus.REQUESTED)
        # Manually force to APPROVED (bypass service to test cancel guard)
        claim.status = AssistantClaimStatus.APPROVED
        claim.save(update_fields=["status"])
        with self.assertRaises(ClaimStateTransitionError):
            cancel_claim(claim=claim)

    def test_state_transition_error_when_completed(self) -> None:
        claim = AssistantGMClaimFactory(status=AssistantClaimStatus.REQUESTED)
        claim.status = AssistantClaimStatus.COMPLETED
        claim.save(update_fields=["status"])
        with self.assertRaises(ClaimStateTransitionError):
            cancel_claim(claim=claim)


class CompleteClaimTests(TestCase):
    """Tests for complete_claim()."""

    def _make_approved_claim(self) -> tuple:
        claim, lead_gm, story = _make_lead_gm_claim()
        claim.status = AssistantClaimStatus.APPROVED
        claim.save(update_fields=["status"])
        return claim, lead_gm, story

    def test_happy_path_lead_gm_completes_approved_claim(self) -> None:
        claim, lead_gm, _ = self._make_approved_claim()
        result = complete_claim(claim=claim, completer=lead_gm)
        self.assertEqual(result.status, AssistantClaimStatus.COMPLETED)

    def test_completion_persisted_to_db(self) -> None:
        claim, lead_gm, _ = self._make_approved_claim()
        complete_claim(claim=claim, completer=lead_gm)
        claim.refresh_from_db()
        self.assertEqual(claim.status, AssistantClaimStatus.COMPLETED)

    def test_state_transition_error_when_not_approved(self) -> None:
        claim, lead_gm, _ = _make_lead_gm_claim()
        # Claim is REQUESTED, not APPROVED
        with self.assertRaises(ClaimStateTransitionError):
            complete_claim(claim=claim, completer=lead_gm)

    def test_state_transition_error_when_cancelled(self) -> None:
        claim, lead_gm, _ = _make_lead_gm_claim()
        claim.status = AssistantClaimStatus.CANCELLED
        claim.save(update_fields=["status"])
        with self.assertRaises(ClaimStateTransitionError):
            complete_claim(claim=claim, completer=lead_gm)

    def test_permission_error_for_non_lead_gm(self) -> None:
        claim, _, _ = self._make_approved_claim()
        outsider = GMProfileFactory()
        with self.assertRaises(ClaimApprovalPermissionError):
            complete_claim(claim=claim, completer=outsider)

    def test_staff_account_can_complete(self) -> None:
        claim, _, _ = self._make_approved_claim()
        staff_gm = GMProfileFactory()
        staff_gm.account.is_staff = True
        staff_gm.account.save()
        result = complete_claim(claim=claim, completer=staff_gm)
        self.assertEqual(result.status, AssistantClaimStatus.COMPLETED)
