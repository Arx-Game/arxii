"""Tests for AssistantGMClaim model and Beat.agm_eligible flag."""

from django.db import IntegrityError
from django.test import TestCase, TransactionTestCase

from world.gm.factories import GMProfileFactory
from world.stories.constants import AssistantClaimStatus
from world.stories.factories import AssistantGMClaimFactory, BeatFactory
from world.stories.models import AssistantGMClaim, Beat


class BeatAGMEligibleFlagTests(TestCase):
    """Tests for the Beat.agm_eligible boolean flag."""

    def test_agm_eligible_default_is_false(self) -> None:
        beat = BeatFactory()
        self.assertFalse(beat.agm_eligible)

    def test_agm_eligible_round_trips_true(self) -> None:
        beat = BeatFactory(agm_eligible=True)
        beat.refresh_from_db()
        self.assertTrue(beat.agm_eligible)

    def test_agm_eligible_can_be_set_and_saved(self) -> None:
        beat = BeatFactory(agm_eligible=False)
        beat.agm_eligible = True
        beat.save(update_fields=["agm_eligible"])
        reloaded = Beat.objects.get(pk=beat.pk)
        self.assertTrue(reloaded.agm_eligible)


class AssistantGMClaimCreationTests(TestCase):
    """Basic creation and field round-trip tests for AssistantGMClaim."""

    def test_claim_creation_defaults(self) -> None:
        claim = AssistantGMClaimFactory()
        self.assertEqual(claim.status, AssistantClaimStatus.REQUESTED)
        self.assertIsNone(claim.approved_by)
        self.assertEqual(claim.rejection_note, "")
        self.assertIsNotNone(claim.beat_id)
        self.assertIsNotNone(claim.assistant_gm_id)

    def test_claim_status_defaults_to_requested(self) -> None:
        gm = GMProfileFactory()
        beat = BeatFactory(agm_eligible=True)
        claim = AssistantGMClaim.objects.create(
            beat=beat,
            assistant_gm=gm,
        )
        self.assertEqual(claim.status, AssistantClaimStatus.REQUESTED)

    def test_claim_str_representation(self) -> None:
        claim = AssistantGMClaimFactory()
        s = str(claim)
        self.assertIn("AssistantGMClaim", s)
        self.assertIn("status=", s)

    def test_claim_round_trips_all_fields(self) -> None:
        gm = GMProfileFactory()
        approver = GMProfileFactory()
        beat = BeatFactory(agm_eligible=True)
        claim = AssistantGMClaim.objects.create(
            beat=beat,
            assistant_gm=gm,
            status=AssistantClaimStatus.APPROVED,
            approved_by=approver,
            rejection_note="",
            framing_note="A framing note for the session.",
        )
        claim.refresh_from_db()
        self.assertEqual(claim.beat_id, beat.pk)
        self.assertEqual(claim.assistant_gm_id, gm.pk)
        self.assertEqual(claim.status, AssistantClaimStatus.APPROVED)
        self.assertEqual(claim.approved_by_id, approver.pk)
        self.assertEqual(claim.framing_note, "A framing note for the session.")

    def test_beat_agm_eligible_required_for_factory(self) -> None:
        """The factory creates beats with agm_eligible=True by default."""
        claim = AssistantGMClaimFactory()
        self.assertTrue(claim.beat.agm_eligible)


class AssistantGMClaimUniqueConstraintTests(TransactionTestCase):
    """Partial unique constraint: only one REQUESTED or APPROVED claim per (beat, agm)."""

    def test_two_requested_claims_for_same_beat_agm_raises(self) -> None:
        gm = GMProfileFactory()
        beat = BeatFactory(agm_eligible=True)
        AssistantGMClaim.objects.create(
            beat=beat, assistant_gm=gm, status=AssistantClaimStatus.REQUESTED
        )
        with self.assertRaises(IntegrityError):
            AssistantGMClaim.objects.create(
                beat=beat, assistant_gm=gm, status=AssistantClaimStatus.REQUESTED
            )

    def test_two_approved_claims_for_same_beat_agm_raises(self) -> None:
        gm = GMProfileFactory()
        beat = BeatFactory(agm_eligible=True)
        approver = GMProfileFactory()
        AssistantGMClaim.objects.create(
            beat=beat,
            assistant_gm=gm,
            status=AssistantClaimStatus.APPROVED,
            approved_by=approver,
        )
        with self.assertRaises(IntegrityError):
            AssistantGMClaim.objects.create(
                beat=beat,
                assistant_gm=gm,
                status=AssistantClaimStatus.APPROVED,
                approved_by=approver,
            )

    def test_rejected_plus_new_requested_for_same_pair_is_allowed(self) -> None:
        """Rejected/cancelled claims do NOT count toward the active constraint."""
        gm = GMProfileFactory()
        beat = BeatFactory(agm_eligible=True)
        approver = GMProfileFactory()
        AssistantGMClaim.objects.create(
            beat=beat, assistant_gm=gm, status=AssistantClaimStatus.REJECTED, approved_by=approver
        )
        # Should not raise — REJECTED is excluded from the partial constraint.
        claim2 = AssistantGMClaim.objects.create(
            beat=beat, assistant_gm=gm, status=AssistantClaimStatus.REQUESTED
        )
        self.assertEqual(claim2.status, AssistantClaimStatus.REQUESTED)

    def test_cancelled_plus_new_requested_for_same_pair_is_allowed(self) -> None:
        gm = GMProfileFactory()
        beat = BeatFactory(agm_eligible=True)
        AssistantGMClaim.objects.create(
            beat=beat, assistant_gm=gm, status=AssistantClaimStatus.CANCELLED
        )
        claim2 = AssistantGMClaim.objects.create(
            beat=beat, assistant_gm=gm, status=AssistantClaimStatus.REQUESTED
        )
        self.assertEqual(claim2.status, AssistantClaimStatus.REQUESTED)

    def test_different_agms_can_each_have_requested_claim(self) -> None:
        gm1 = GMProfileFactory()
        gm2 = GMProfileFactory()
        beat = BeatFactory(agm_eligible=True)
        claim1 = AssistantGMClaim.objects.create(
            beat=beat, assistant_gm=gm1, status=AssistantClaimStatus.REQUESTED
        )
        claim2 = AssistantGMClaim.objects.create(
            beat=beat, assistant_gm=gm2, status=AssistantClaimStatus.REQUESTED
        )
        self.assertEqual(claim1.assistant_gm_id, gm1.pk)
        self.assertEqual(claim2.assistant_gm_id, gm2.pk)
