"""Tests for GMRosterInvite ViewSet and GMInviteClaimView."""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.gm.factories import (
    GMProfileFactory,
    GMRosterInviteFactory,
    GMTableFactory,
)
from world.roster.factories import RosterEntryFactory
from world.stories.factories import StoryFactory
from world.stories.models import StoryParticipation


class GMInviteCreateTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.gm_account = AccountFactory()
        cls.gm = GMProfileFactory(account=cls.gm_account)
        cls.table = GMTableFactory(gm=cls.gm)
        cls.entry = RosterEntryFactory()
        story = StoryFactory(primary_table=cls.table)
        StoryParticipation.objects.create(
            story=story,
            character=cls.entry.character_sheet.character,
            is_active=True,
        )
        cls.other_gm_account = AccountFactory()
        cls.other_gm = GMProfileFactory(account=cls.other_gm_account)
        cls.other_entry = RosterEntryFactory()
        other_story = StoryFactory(primary_table=GMTableFactory(gm=cls.other_gm))
        StoryParticipation.objects.create(
            story=other_story,
            character=cls.other_entry.character_sheet.character,
            is_active=True,
        )

    def setUp(self) -> None:
        self.client = APIClient()

    def test_gm_creates_invite_for_own_character(self) -> None:
        self.client.force_authenticate(user=self.gm_account)
        url = reverse("gm:gm-invite-list")
        resp = self.client.post(
            url,
            {"roster_entry": self.entry.pk, "is_public": True},
            format="json",
        )
        assert resp.status_code == 201, resp.data
        assert resp.data["created_by"] == self.gm.pk
        assert resp.data["code"]

    def test_gm_cannot_create_invite_for_other_gms_character(self) -> None:
        self.client.force_authenticate(user=self.gm_account)
        url = reverse("gm:gm-invite-list")
        resp = self.client.post(
            url,
            {"roster_entry": self.other_entry.pk, "is_public": True},
            format="json",
        )
        assert resp.status_code == 400

    def test_unauthenticated_rejected(self) -> None:
        url = reverse("gm:gm-invite-list")
        resp = self.client.post(url, {"roster_entry": self.entry.pk}, format="json")
        assert resp.status_code in (401, 403)

    def test_non_gm_user_forbidden(self) -> None:
        random_user = AccountFactory()
        self.client.force_authenticate(user=random_user)
        url = reverse("gm:gm-invite-list")
        resp = self.client.post(url, {"roster_entry": self.entry.pk}, format="json")
        assert resp.status_code == 403


class GMInviteListTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(is_superuser=True)
        cls.gm_account = AccountFactory()
        cls.gm = GMProfileFactory(account=cls.gm_account)
        cls.other_gm = GMProfileFactory()
        cls.my_invite = GMRosterInviteFactory(created_by=cls.gm)
        cls.other_invite = GMRosterInviteFactory(created_by=cls.other_gm)

    def setUp(self) -> None:
        self.client = APIClient()

    def test_gm_sees_only_own_invites(self) -> None:
        self.client.force_authenticate(user=self.gm_account)
        url = reverse("gm:gm-invite-list")
        resp = self.client.get(url)
        assert resp.status_code == 200
        ids = {item["id"] for item in resp.data["results"]}
        assert self.my_invite.pk in ids
        assert self.other_invite.pk not in ids

    def test_staff_sees_all_invites(self) -> None:
        self.client.force_authenticate(user=self.staff)
        url = reverse("gm:gm-invite-list")
        resp = self.client.get(url)
        assert resp.status_code == 200
        ids = {item["id"] for item in resp.data["results"]}
        assert self.my_invite.pk in ids
        assert self.other_invite.pk in ids


class GMInviteRevokeTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.gm_account = AccountFactory()
        cls.gm = GMProfileFactory(account=cls.gm_account)
        cls.other_gm_account = AccountFactory()
        cls.other_gm = GMProfileFactory(account=cls.other_gm_account)

    def setUp(self) -> None:
        self.client = APIClient()
        self.invite = GMRosterInviteFactory(created_by=self.gm)

    def test_gm_revokes_own_unclaimed_invite(self) -> None:
        self.client.force_authenticate(user=self.gm_account)
        url = reverse("gm:gm-invite-detail", args=[self.invite.pk])
        resp = self.client.delete(url)
        assert resp.status_code == 204
        self.invite.refresh_from_db()
        assert self.invite.is_expired is True

    def test_gm_cannot_revoke_other_gms_invite(self) -> None:
        self.client.force_authenticate(user=self.other_gm_account)
        url = reverse("gm:gm-invite-detail", args=[self.invite.pk])
        resp = self.client.delete(url)
        # Other GM's queryset excludes this invite — 404
        assert resp.status_code == 404

    def test_cannot_revoke_claimed_invite(self) -> None:
        self.invite.claimed_at = timezone.now()
        self.invite.claimed_by = AccountFactory()
        self.invite.save(update_fields=["claimed_at", "claimed_by"])
        self.client.force_authenticate(user=self.gm_account)
        url = reverse("gm:gm-invite-detail", args=[self.invite.pk])
        resp = self.client.delete(url)
        assert resp.status_code == 400


class GMInviteClaimTest(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.account = AccountFactory(email="claimer@example.com")
        self.invite = GMRosterInviteFactory(is_public=True)

    def test_claim_valid_public_invite(self) -> None:
        self.client.force_authenticate(user=self.account)
        url = reverse("gm:gm-invite-claim")
        resp = self.client.post(url, {"code": self.invite.code}, format="json")
        assert resp.status_code == 201
        assert "application_id" in resp.data

    def test_missing_code_returns_400(self) -> None:
        self.client.force_authenticate(user=self.account)
        url = reverse("gm:gm-invite-claim")
        resp = self.client.post(url, {}, format="json")
        assert resp.status_code == 400
        assert "code" in resp.data

    def test_invalid_code_returns_400(self) -> None:
        self.client.force_authenticate(user=self.account)
        url = reverse("gm:gm-invite-claim")
        resp = self.client.post(url, {"code": "not-a-real-code"}, format="json")
        assert resp.status_code == 400

    def test_expired_invite_returns_400(self) -> None:
        self.client.force_authenticate(user=self.account)
        past = timezone.now() - timedelta(days=1)
        expired = GMRosterInviteFactory(is_public=True, expires_at=past)
        url = reverse("gm:gm-invite-claim")
        resp = self.client.post(url, {"code": expired.code}, format="json")
        assert resp.status_code == 400

    def test_unauthenticated_rejected(self) -> None:
        url = reverse("gm:gm-invite-claim")
        resp = self.client.post(url, {"code": self.invite.code}, format="json")
        assert resp.status_code in (401, 403)
