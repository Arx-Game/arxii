"""Tests for the TableUpdateRequest framework (#2631)."""

from __future__ import annotations

from django.test import TestCase
from django.utils import timezone

from world.character_sheets.models import ProfileTextVersion
from world.character_sheets.types import ProfileTextField
from world.distinctions.factories import (
    CharacterDistinctionFactory,
    DistinctionFactory,
)
from world.distinctions.types import DistinctionChangeAction
from world.gm.constants import TableRequestKind, TableRequestStatus
from world.gm.factories import (
    GMProfileFactory,
    GMTableMembershipFactory,
)
from world.gm.services import (
    TableRequestError,
    mark_requests_completed_for_authorization,
    signoff_table_update_request,
    submit_distinction_change_request,
    submit_profile_text_request,
    withdraw_table_update_request,
)


class SubmitRequestTests(TestCase):
    def setUp(self):
        self.membership = GMTableMembershipFactory()
        self.sheet = self.membership.persona.character_sheet

    def test_submit_profile_text_request(self):
        request = submit_profile_text_request(
            self.membership,
            field=ProfileTextField.BACKGROUND,
            proposed_text="A new chapter.",
            reasoning="The siege changed everything.",
        )
        assert request.status == TableRequestStatus.PENDING
        assert request.kind == TableRequestKind.PROFILE_TEXT
        assert request.profile_text_details.proposed_text == "A new chapter."

    def test_submit_rejects_unknown_field(self):
        with self.assertRaises(TableRequestError):
            submit_profile_text_request(
                self.membership,
                field="obituary",
                proposed_text="text",
                reasoning="reason",
            )

    def test_submit_rejects_left_membership(self):
        self.membership.left_at = timezone.now()
        self.membership.save()
        with self.assertRaises(TableRequestError):
            submit_profile_text_request(
                self.membership,
                field=ProfileTextField.BACKGROUND,
                proposed_text="text",
                reasoning="reason",
            )

    def test_submit_distinction_change_request(self):
        distinction = DistinctionFactory(cost_per_rank=5, max_rank=1)
        request = submit_distinction_change_request(
            self.membership,
            action=DistinctionChangeAction.ADD,
            distinction=distinction,
            reasoning="Earned it in the story.",
        )
        assert request.kind == TableRequestKind.DISTINCTION_CHANGE
        assert request.distinction_details.distinction == distinction

    def test_submit_rejects_other_characters_distinction(self):
        other = CharacterDistinctionFactory()  # different sheet
        with self.assertRaises(TableRequestError):
            submit_distinction_change_request(
                self.membership,
                action=DistinctionChangeAction.REMOVE,
                character_distinction=other,
                reasoning="reason",
            )


class SignoffTests(TestCase):
    def setUp(self):
        self.membership = GMTableMembershipFactory()
        self.gm = self.membership.table.gm
        self.sheet = self.membership.persona.character_sheet

    def test_wrong_gm_cannot_signoff(self):
        request = submit_profile_text_request(
            self.membership,
            field=ProfileTextField.BACKGROUND,
            proposed_text="text",
            reasoning="reason",
        )
        stranger = GMProfileFactory()
        with self.assertRaises(TableRequestError):
            signoff_table_update_request(request, stranger, approve=True)

    def test_approve_profile_text_applies_and_completes(self):
        profile = self.sheet.true_profile
        profile.background = "The old story."
        profile.save(update_fields=["background"])

        request = submit_profile_text_request(
            self.membership,
            field=ProfileTextField.BACKGROUND,
            proposed_text="The new story.",
            reasoning="Growth.",
        )
        signoff_table_update_request(request, self.gm, approve=True, notes="Fits the arc.")

        request.refresh_from_db()
        assert request.status == TableRequestStatus.COMPLETED
        assert request.completed_at is not None
        profile.refresh_from_db()
        assert profile.background == "The new story."
        versions = ProfileTextVersion.objects.filter(
            profile=profile, field=ProfileTextField.BACKGROUND
        ).order_by("created_at")
        assert [v.text for v in versions] == ["The old story.", "The new story."]
        assert request.profile_text_details.applied_version == versions.last()

    def test_approve_distinction_creates_authorization(self):
        distinction = DistinctionFactory(cost_per_rank=5, max_rank=2)
        request = submit_distinction_change_request(
            self.membership,
            action=DistinctionChangeAction.ADD,
            distinction=distinction,
            rank=2,
            reasoning="Earned it.",
        )
        signoff_table_update_request(request, self.gm, approve=True)

        request.refresh_from_db()
        assert request.status == TableRequestStatus.APPROVED
        auth = request.distinction_details.authorization
        assert auth is not None
        assert auth.rank == 2
        assert auth.xp_cost == 20  # 2 × 5 × 2
        assert auth.character_sheet == self.sheet

    def test_reject_notifies_and_terminates(self):
        from world.narrative.models import NarrativeMessage

        request = submit_profile_text_request(
            self.membership,
            field=ProfileTextField.BACKGROUND,
            proposed_text="text",
            reasoning="reason",
        )
        before = NarrativeMessage.objects.count()
        signoff_table_update_request(request, self.gm, approve=False, notes="Not yet.")

        request.refresh_from_db()
        assert request.status == TableRequestStatus.REJECTED
        assert request.gm_notes == "Not yet."
        assert NarrativeMessage.objects.count() == before + 1

    def test_double_signoff_rejected(self):
        request = submit_profile_text_request(
            self.membership,
            field=ProfileTextField.BACKGROUND,
            proposed_text="text",
            reasoning="reason",
        )
        signoff_table_update_request(request, self.gm, approve=True)
        with self.assertRaises(TableRequestError):
            signoff_table_update_request(request, self.gm, approve=False)


class WithdrawAndCompletionTests(TestCase):
    def setUp(self):
        self.membership = GMTableMembershipFactory()
        self.gm = self.membership.table.gm

    def test_withdraw_pending(self):
        request = submit_profile_text_request(
            self.membership,
            field=ProfileTextField.BACKGROUND,
            proposed_text="text",
            reasoning="reason",
        )
        withdraw_table_update_request(request)
        request.refresh_from_db()
        assert request.status == TableRequestStatus.WITHDRAWN

    def test_withdraw_resolved_rejected(self):
        request = submit_profile_text_request(
            self.membership,
            field=ProfileTextField.BACKGROUND,
            proposed_text="text",
            reasoning="reason",
        )
        signoff_table_update_request(request, self.gm, approve=False)
        with self.assertRaises(TableRequestError):
            withdraw_table_update_request(request)

    def test_mark_completed_for_authorization(self):
        distinction = DistinctionFactory(cost_per_rank=5, max_rank=1)
        request = submit_distinction_change_request(
            self.membership,
            action=DistinctionChangeAction.ADD,
            distinction=distinction,
            reasoning="Earned it.",
        )
        signoff_table_update_request(request, self.gm, approve=True)
        request.refresh_from_db()
        auth = request.distinction_details.authorization

        count = mark_requests_completed_for_authorization(auth)
        assert count == 1
        request.refresh_from_db()
        assert request.status == TableRequestStatus.COMPLETED
