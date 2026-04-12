"""Tests for GM system views."""

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.gm.constants import GMApplicationStatus
from world.gm.factories import GMApplicationFactory


class GMApplicationCreateTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = AccountFactory()

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_authenticated_user_can_create(self) -> None:
        url = reverse("gm:gm-application-list")
        text = (
            "I want to GM because I love telling stories and collaborating with players "
            "to build memorable scenes."
        )
        resp = self.client.post(url, {"application_text": text}, format="json")
        assert resp.status_code == 201
        assert resp.data["application_text"] == text

    def test_unauthenticated_cannot_create(self) -> None:
        self.client.force_authenticate(user=None)
        url = reverse("gm:gm-application-list")
        text = "a" * 60
        resp = self.client.post(url, {"application_text": text}, format="json")
        assert resp.status_code in (401, 403)  # DRF returns 403 with SessionAuth


class GMApplicationStaffTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(is_superuser=True)
        cls.user = AccountFactory()
        cls.application = GMApplicationFactory()

    def setUp(self) -> None:
        self.client = APIClient()

    def test_staff_can_list(self) -> None:
        self.client.force_authenticate(user=self.staff)
        url = reverse("gm:gm-application-list")
        resp = self.client.get(url)
        assert resp.status_code == 200

    def test_non_staff_cannot_list(self) -> None:
        self.client.force_authenticate(user=self.user)
        url = reverse("gm:gm-application-list")
        resp = self.client.get(url)
        assert resp.status_code == 403

    def test_staff_can_update_status(self) -> None:
        self.client.force_authenticate(user=self.staff)
        url = reverse("gm:gm-application-detail", args=[self.application.pk])
        resp = self.client.patch(
            url,
            {
                "status": GMApplicationStatus.APPROVED,
                "staff_response": "Welcome!",
            },
            format="json",
        )
        assert resp.status_code == 200
        self.application.refresh_from_db()
        assert self.application.status == GMApplicationStatus.APPROVED

    def test_status_filter_returns_only_matching(self) -> None:
        # Existing fixture self.application is PENDING
        # Create an APPROVED application
        other = GMApplicationFactory(status=GMApplicationStatus.APPROVED)

        self.client.force_authenticate(user=self.staff)
        url = reverse("gm:gm-application-list")

        pending_resp = self.client.get(url, {"status": "pending"})
        assert pending_resp.status_code == 200
        pending_ids = {item["id"] for item in pending_resp.data["results"]}
        assert self.application.pk in pending_ids
        assert other.pk not in pending_ids

        approved_resp = self.client.get(url, {"status": "approved"})
        approved_ids = {item["id"] for item in approved_resp.data["results"]}
        assert other.pk in approved_ids
        assert self.application.pk not in approved_ids

    def test_non_superuser_staff_can_list(self) -> None:
        staff_user = AccountFactory(is_staff=True, is_superuser=False)
        self.client.force_authenticate(user=staff_user)
        url = reverse("gm:gm-application-list")
        resp = self.client.get(url)
        assert resp.status_code == 200


class GMApplicationApprovalWorkflowTest(TestCase):
    """Test the approval workflow creates GMProfile and stamps reviewed_by."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(is_superuser=True)
        cls.applicant = AccountFactory()

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.staff)
        # Create the application in setUp (not setUpTestData) to avoid
        # SharedMemoryModel caching stale in-memory status across tests
        # when the DB is rolled back.
        self.application = GMApplicationFactory(account=self.applicant)

    def test_approving_creates_gm_profile(self) -> None:
        from world.gm.models import GMProfile

        url = reverse("gm:gm-application-detail", args=[self.application.pk])
        self.client.patch(
            url,
            {"status": GMApplicationStatus.APPROVED},
            format="json",
        )
        assert GMProfile.objects.filter(account=self.applicant).exists()

    def test_update_stamps_reviewed_by(self) -> None:
        url = reverse("gm:gm-application-detail", args=[self.application.pk])
        self.client.patch(
            url,
            {"staff_response": "looking good"},
            format="json",
        )
        self.application.refresh_from_db()
        assert self.application.reviewed_by == self.staff

    def test_non_approval_update_does_not_create_profile(self) -> None:
        from world.gm.models import GMProfile

        url = reverse("gm:gm-application-detail", args=[self.application.pk])
        self.client.patch(
            url,
            {"staff_response": "need more info"},
            format="json",
        )
        assert not GMProfile.objects.filter(account=self.applicant).exists()

    def test_re_approval_keeps_original_profile(self) -> None:
        from world.gm.models import GMProfile

        url = reverse("gm:gm-application-detail", args=[self.application.pk])
        # First approval
        self.client.patch(url, {"status": GMApplicationStatus.APPROVED}, format="json")
        profile = GMProfile.objects.get(account=self.applicant)
        original_approved_at = profile.approved_at
        # Revert to pending
        self.client.patch(url, {"status": GMApplicationStatus.PENDING}, format="json")
        # Re-approve
        self.client.patch(url, {"status": GMApplicationStatus.APPROVED}, format="json")
        # Still only one profile
        assert GMProfile.objects.filter(account=self.applicant).count() == 1
        profile.refresh_from_db()
        # approved_at is unchanged (get_or_create doesn't update defaults)
        assert profile.approved_at == original_approved_at


class GMApplicationDuplicateGuardTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = AccountFactory()

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_cannot_submit_while_pending(self) -> None:
        url = reverse("gm:gm-application-list")
        first_text = "first application " + ("x" * 60)
        second_text = "second application " + ("y" * 60)
        r1 = self.client.post(url, {"application_text": first_text}, format="json")
        assert r1.status_code == 201
        r2 = self.client.post(url, {"application_text": second_text}, format="json")
        assert r2.status_code == 400

    def test_cannot_submit_if_already_gm(self) -> None:
        from world.gm.factories import GMProfileFactory

        GMProfileFactory(account=self.user)
        url = reverse("gm:gm-application-list")
        text = "I would like to apply " + ("z" * 60)
        resp = self.client.post(url, {"application_text": text}, format="json")
        assert resp.status_code == 400


class GMApplicationValidationTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = AccountFactory()

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_empty_application_rejected(self) -> None:
        url = reverse("gm:gm-application-list")
        resp = self.client.post(url, {"application_text": ""}, format="json")
        assert resp.status_code == 400

    def test_too_short_application_rejected(self) -> None:
        url = reverse("gm:gm-application-list")
        resp = self.client.post(url, {"application_text": "too short"}, format="json")
        assert resp.status_code == 400
