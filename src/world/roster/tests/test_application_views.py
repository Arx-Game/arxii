"""Tests for the staff roster-application review endpoints (#3265)."""

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.roster.factories import (
    RosterApplicationFactory,
    RosterEntryFactory,
    RosterFactory,
)
from world.roster.models import RosterApplication, RosterTenure
from world.roster.models.choices import ApplicationStatus, RosterType


class StaffRosterApplicationViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.player = AccountFactory(is_staff=False)
        cls.available = RosterFactory(roster_type=RosterType.AVAILABLE, name="Available")
        cls.active = RosterFactory(roster_type=RosterType.ACTIVE, name="Active Characters")
        cls.pending_app = RosterApplicationFactory(status=ApplicationStatus.PENDING)
        RosterEntryFactory(character_sheet=cls.pending_app.character, roster=cls.available)
        cls.denied_app = RosterApplicationFactory(status=ApplicationStatus.DENIED)

    def setUp(self):
        self.client = APIClient()

    def test_anonymous_rejected(self):
        url = reverse("roster:applications-list")
        response = self.client.get(url)
        assert response.status_code == 403

    def test_non_staff_rejected(self):
        self.client.force_authenticate(self.player)
        url = reverse("roster:applications-list")
        response = self.client.get(url)
        assert response.status_code == 403

    def test_list_defaults_to_pending(self):
        self.client.force_authenticate(self.staff)
        url = reverse("roster:applications-list")
        response = self.client.get(url)
        assert response.status_code == 200
        ids = [row["id"] for row in response.data["results"]]
        assert self.pending_app.id in ids
        assert self.denied_app.id not in ids

    def test_list_status_filter(self):
        self.client.force_authenticate(self.staff)
        url = reverse("roster:applications-list")
        response = self.client.get(url, {"status": ApplicationStatus.DENIED})
        assert response.status_code == 200
        ids = [row["id"] for row in response.data["results"]]
        assert ids == [self.denied_app.id]

    def test_detail_includes_policy_info_and_character_name(self):
        self.client.force_authenticate(self.staff)
        url = reverse("roster:applications-detail", args=[self.pending_app.id])
        response = self.client.get(url)
        assert response.status_code == 200
        expected_name = self.pending_app.character.character.db_key
        assert response.data["character_name"] == expected_name
        assert "policy_review_info" in response.data
        assert "application_text" in response.data

    def test_review_approve_creates_tenure_and_moves_shelf(self):
        self.client.force_authenticate(self.staff)
        url = reverse("roster:applications-review", args=[self.pending_app.id])
        response = self.client.post(url, {"action": "approve"}, format="json")
        assert response.status_code == 200, response.data
        self.pending_app.refresh_from_db()
        assert self.pending_app.status == ApplicationStatus.APPROVED
        tenure = RosterTenure.objects.current().get(
            roster_entry=self.pending_app.character.roster_entry
        )
        assert tenure.player_data == self.pending_app.player_data
        assert self.pending_app.character.roster_entry.roster == self.active

    def test_review_deny_records_notes(self):
        app = RosterApplicationFactory(status=ApplicationStatus.PENDING)
        RosterEntryFactory(character_sheet=app.character, roster=self.available)
        self.client.force_authenticate(self.staff)
        url = reverse("roster:applications-review", args=[app.id])
        response = self.client.post(
            url, {"action": "deny", "review_notes": "Not a fit."}, format="json"
        )
        assert response.status_code == 200, response.data
        app.refresh_from_db()
        assert app.status == ApplicationStatus.DENIED
        assert app.review_notes == "Not a fit."

    def test_review_rejects_non_pending(self):
        self.client.force_authenticate(self.staff)
        url = reverse("roster:applications-review", args=[self.denied_app.id])
        response = self.client.post(url, {"action": "approve"}, format="json")
        assert response.status_code == 400

    def test_pending_count(self):
        self.client.force_authenticate(self.staff)
        url = reverse("roster:applications-pending-count")
        response = self.client.get(url)
        assert response.status_code == 200
        assert response.data["count"] == RosterApplication.objects.pending().count()
