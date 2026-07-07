"""Tests for the promote + evidence endpoints on GMProfileViewSet (#2000 task 6)."""

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory
from world.gm.models import GMLevelChange


class PromoteGmViewTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(is_staff=True)
        cls.player = AccountFactory()
        cls.profile = GMProfileFactory(level=GMLevel.STARTING)

    def setUp(self) -> None:
        self.client = APIClient()

    def _url(self, profile=None) -> str:
        return reverse("gm:gm-profile-promote", args=[(profile or self.profile).pk])

    def test_staff_can_promote(self) -> None:
        self.client.force_authenticate(user=self.staff)
        resp = self.client.post(
            self._url(),
            {"new_level": GMLevel.JUNIOR, "reason": "Ran three tables well."},
            format="json",
        )
        assert resp.status_code in (200, 201)
        self.profile.refresh_from_db()
        assert self.profile.level == GMLevel.JUNIOR
        change = GMLevelChange.objects.get(profile=self.profile)
        assert change.old_level == GMLevel.STARTING
        assert change.new_level == GMLevel.JUNIOR
        assert change.changed_by == self.staff
        assert change.reason == "Ran three tables well."

    def test_non_staff_cannot_promote(self) -> None:
        self.client.force_authenticate(user=self.player)
        resp = self.client.post(
            self._url(),
            {"new_level": GMLevel.JUNIOR, "reason": "Nope."},
            format="json",
        )
        assert resp.status_code == 403
        self.profile.refresh_from_db()
        assert self.profile.level == GMLevel.STARTING
        assert not GMLevelChange.objects.filter(profile=self.profile).exists()

    def test_same_level_returns_400(self) -> None:
        self.client.force_authenticate(user=self.staff)
        resp = self.client.post(
            self._url(),
            {"new_level": GMLevel.STARTING, "reason": "No-op."},
            format="json",
        )
        assert resp.status_code == 400
        self.profile.refresh_from_db()
        assert self.profile.level == GMLevel.STARTING
        assert not GMLevelChange.objects.filter(profile=self.profile).exists()

    def test_unknown_level_returns_400(self) -> None:
        self.client.force_authenticate(user=self.staff)
        resp = self.client.post(
            self._url(),
            {"new_level": "not-a-real-level", "reason": "Bogus."},
            format="json",
        )
        assert resp.status_code == 400
        self.profile.refresh_from_db()
        assert self.profile.level == GMLevel.STARTING
        assert not GMLevelChange.objects.filter(profile=self.profile).exists()

    def test_blank_reason_returns_400(self) -> None:
        self.client.force_authenticate(user=self.staff)
        resp = self.client.post(
            self._url(),
            {"new_level": GMLevel.JUNIOR, "reason": ""},
            format="json",
        )
        assert resp.status_code == 400
        self.profile.refresh_from_db()
        assert self.profile.level == GMLevel.STARTING


class GmEvidenceViewTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(is_staff=True)
        cls.player = AccountFactory()
        cls.profile = GMProfileFactory(level=GMLevel.GM)

    def setUp(self) -> None:
        self.client = APIClient()

    def _url(self) -> str:
        return reverse("gm:gm-profile-evidence", args=[self.profile.pk])

    def test_staff_can_view_evidence(self) -> None:
        self.client.force_authenticate(user=self.staff)
        resp = self.client.get(self._url())
        assert resp.status_code == 200
        assert resp.data["profile_id"] == self.profile.pk
        assert resp.data["level"] == GMLevel.GM
        assert resp.data["stories_running"] == 0
        assert resp.data["beats_completed_by_risk"] == {}
        assert resp.data["feedback_by_category"] == []
        assert resp.data["level_changes"] == []

    def test_evidence_includes_level_changes(self) -> None:
        from world.gm.factories import GMLevelChangeFactory

        change = GMLevelChangeFactory(
            profile=self.profile,
            old_level=GMLevel.STARTING,
            new_level=GMLevel.GM,
            changed_by=self.staff,
            reason="Great tables.",
        )
        self.client.force_authenticate(user=self.staff)
        resp = self.client.get(self._url())
        assert resp.status_code == 200
        assert len(resp.data["level_changes"]) == 1
        row = resp.data["level_changes"][0]
        assert row["id"] == change.pk
        assert row["old_level"] == GMLevel.STARTING
        assert row["new_level"] == GMLevel.GM
        assert row["reason"] == "Great tables."

    def test_non_staff_cannot_view_evidence(self) -> None:
        self.client.force_authenticate(user=self.player)
        resp = self.client.get(self._url())
        assert resp.status_code == 403
