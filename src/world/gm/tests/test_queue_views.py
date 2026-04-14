"""Tests for GMApplicationQueueView and GMApplicationActionView."""

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.roster.factories import RosterApplicationFactory, RosterEntryFactory
from world.stories.factories import StoryFactory
from world.stories.models import StoryParticipation


def _attach_pending_application(gm):
    """Create a roster entry + story participation + pending application
    all overseen by ``gm``. Returns (entry, application).
    """
    table = GMTableFactory(gm=gm)
    entry = RosterEntryFactory()
    story = StoryFactory(primary_table=table)
    StoryParticipation.objects.create(
        story=story,
        character=entry.character_sheet.character,
        is_active=True,
    )
    application = RosterApplicationFactory(character=entry.character_sheet.character)
    return entry, application


class GMApplicationQueueViewTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.gm_account = AccountFactory()
        cls.gm = GMProfileFactory(account=cls.gm_account)
        cls.other_gm_account = AccountFactory()
        cls.other_gm = GMProfileFactory(account=cls.other_gm_account)

        _, cls.my_app = _attach_pending_application(cls.gm)
        _, cls.other_app = _attach_pending_application(cls.other_gm)

    def setUp(self) -> None:
        self.client = APIClient()

    def test_gm_sees_pending_apps_for_own_tables(self) -> None:
        self.client.force_authenticate(user=self.gm_account)
        url = reverse("gm:gm-application-queue")
        resp = self.client.get(url)
        assert resp.status_code == 200
        ids = {item["id"] for item in resp.data["results"]}
        assert self.my_app.pk in ids
        assert self.other_app.pk not in ids

    def test_non_gm_user_rejected(self) -> None:
        random_user = AccountFactory()
        self.client.force_authenticate(user=random_user)
        url = reverse("gm:gm-application-queue")
        resp = self.client.get(url)
        assert resp.status_code == 403

    def test_unauthenticated_rejected(self) -> None:
        url = reverse("gm:gm-application-queue")
        resp = self.client.get(url)
        assert resp.status_code in (401, 403)


class GMApplicationActionViewTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.gm_account = AccountFactory()
        cls.gm = GMProfileFactory(account=cls.gm_account)
        cls.other_gm_account = AccountFactory()
        cls.other_gm = GMProfileFactory(account=cls.other_gm_account)

    def setUp(self) -> None:
        self.client = APIClient()
        _, self.app = _attach_pending_application(self.gm)

    def test_gm_can_approve_queue_application(self) -> None:
        from world.roster.models.choices import ApplicationStatus

        self.client.force_authenticate(user=self.gm_account)
        url = reverse("gm:gm-application-action", args=[self.app.pk, "approve"])
        resp = self.client.post(url, {}, format="json")
        assert resp.status_code == 200, resp.data
        self.app.refresh_from_db()
        assert self.app.status == ApplicationStatus.APPROVED

    def test_gm_cannot_approve_other_gms_application(self) -> None:
        self.client.force_authenticate(user=self.other_gm_account)
        url = reverse("gm:gm-application-action", args=[self.app.pk, "approve"])
        resp = self.client.post(url, {}, format="json")
        assert resp.status_code == 400

    def test_gm_can_deny_with_review_notes(self) -> None:
        from world.roster.models.choices import ApplicationStatus

        self.client.force_authenticate(user=self.gm_account)
        url = reverse("gm:gm-application-action", args=[self.app.pk, "deny"])
        resp = self.client.post(url, {"review_notes": "Not a fit"}, format="json")
        assert resp.status_code == 200, resp.data
        self.app.refresh_from_db()
        assert self.app.status == ApplicationStatus.DENIED
        assert self.app.review_notes == "Not a fit"

    def test_invalid_action_returns_400(self) -> None:
        self.client.force_authenticate(user=self.gm_account)
        url = reverse("gm:gm-application-action", args=[self.app.pk, "nuke"])
        resp = self.client.post(url, {}, format="json")
        assert resp.status_code == 400

    def test_non_gm_user_forbidden(self) -> None:
        random_user = AccountFactory()
        self.client.force_authenticate(user=random_user)
        url = reverse("gm:gm-application-action", args=[self.app.pk, "approve"])
        resp = self.client.post(url, {}, format="json")
        assert resp.status_code == 403

    def test_unauthenticated_rejected(self) -> None:
        url = reverse("gm:gm-application-action", args=[self.app.pk, "approve"])
        resp = self.client.post(url, {}, format="json")
        assert resp.status_code in (401, 403)
