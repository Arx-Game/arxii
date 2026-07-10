"""Tests for CatalogSuggestionViewSet (#2127) -- staff triage of the suggestion inbox.

No create-via-API coverage here: creation only happens through
``SubmitCatalogSuggestionAction`` (see ``actions/tests/test_gm_catalog_actions.py``
and ``commands/tests/test_gm_ops_catalog.py``), never a direct DRF POST.
"""

from __future__ import annotations

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.gm.factories import CatalogSuggestionFactory
from world.player_submissions.constants import SubmissionStatus


class CatalogSuggestionViewSetStaffTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(is_superuser=True)
        cls.user = AccountFactory()
        cls.suggestion = CatalogSuggestionFactory()

    def setUp(self) -> None:
        self.client = APIClient()

    def test_staff_can_list(self) -> None:
        self.client.force_authenticate(user=self.staff)
        url = reverse("gm:catalog-suggestion-list")
        resp = self.client.get(url)
        assert resp.status_code == 200

    def test_non_staff_cannot_list(self) -> None:
        self.client.force_authenticate(user=self.user)
        url = reverse("gm:catalog-suggestion-list")
        resp = self.client.get(url)
        assert resp.status_code == 403

    def test_unauthenticated_cannot_list(self) -> None:
        url = reverse("gm:catalog-suggestion-list")
        resp = self.client.get(url)
        assert resp.status_code in (401, 403)

    def test_staff_can_retrieve(self) -> None:
        self.client.force_authenticate(user=self.staff)
        url = reverse("gm:catalog-suggestion-detail", args=[self.suggestion.pk])
        resp = self.client.get(url)
        assert resp.status_code == 200
        assert resp.data["id"] == self.suggestion.pk

    def test_no_create_action_exposed(self) -> None:
        """No POST endpoint -- creation only happens through the Action."""
        self.client.force_authenticate(user=self.staff)
        url = reverse("gm:catalog-suggestion-list")
        resp = self.client.post(url, {"proposal_kind": "other", "proposal_text": "x"})
        assert resp.status_code == 405

    def test_staff_update_sets_reviewer_and_resolved_at(self) -> None:
        self.client.force_authenticate(user=self.staff)
        url = reverse("gm:catalog-suggestion-detail", args=[self.suggestion.pk])
        resp = self.client.patch(
            url,
            {"status": SubmissionStatus.REVIEWED, "review_notes": "Looks good."},
            format="json",
        )
        assert resp.status_code == 200
        self.suggestion.refresh_from_db()
        assert self.suggestion.status == SubmissionStatus.REVIEWED
        assert self.suggestion.reviewer_id == self.staff.pk
        assert self.suggestion.resolved_at is not None

    def test_update_to_open_does_not_stamp_resolved_at(self) -> None:
        self.client.force_authenticate(user=self.staff)
        url = reverse("gm:catalog-suggestion-detail", args=[self.suggestion.pk])
        resp = self.client.patch(url, {"review_notes": "note only"}, format="json")
        assert resp.status_code == 200
        self.suggestion.refresh_from_db()
        assert self.suggestion.status == SubmissionStatus.OPEN
        assert self.suggestion.resolved_at is None

    def test_proposal_text_is_read_only(self) -> None:
        original_text = self.suggestion.proposal_text
        self.client.force_authenticate(user=self.staff)
        url = reverse("gm:catalog-suggestion-detail", args=[self.suggestion.pk])
        resp = self.client.patch(url, {"proposal_text": "rewritten"}, format="json")
        assert resp.status_code == 200
        self.suggestion.refresh_from_db()
        assert self.suggestion.proposal_text == original_text
