"""API tests for /api/narrative/category-mutes/ (#1522).

The web face of the category squelch (e.g. silence the WEATHER echo). Mirrors the story-mute
ViewSet tests: list/create/delete scoped to the requesting account.
"""

from rest_framework import status
from rest_framework.test import APITestCase

from core_management.test_utils import suppress_permission_errors
from evennia_extensions.factories import AccountFactory
from world.narrative.constants import NarrativeCategory
from world.narrative.models import UserCategoryMute

MUTES_URL = "/api/narrative/category-mutes/"


class UserCategoryMuteListTest(APITestCase):
    """GET /api/narrative/category-mutes/ — list own mutes."""

    @classmethod
    def setUpTestData(cls):
        cls.user = AccountFactory()
        cls.other = AccountFactory()

    def test_lists_own_mutes(self):
        UserCategoryMute.objects.create(account=self.user, category=NarrativeCategory.WEATHER)
        UserCategoryMute.objects.create(account=self.other, category=NarrativeCategory.WEATHER)
        self.client.force_authenticate(user=self.user)
        response = self.client.get(MUTES_URL)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        assert response.data["results"][0]["category"] == NarrativeCategory.WEATHER

    @suppress_permission_errors
    def test_unauthenticated_rejected(self):
        response = self.client.get(MUTES_URL)
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )


class UserCategoryMuteCreateTest(APITestCase):
    """POST /api/narrative/category-mutes/ — mute a category."""

    def setUp(self):
        self.user = AccountFactory()

    def test_create_mute(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            MUTES_URL, {"category": NarrativeCategory.WEATHER}, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert UserCategoryMute.objects.filter(
            account=self.user, category=NarrativeCategory.WEATHER
        ).exists()

    def test_mute_response_shape(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            MUTES_URL, {"category": NarrativeCategory.WEATHER}, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.data
        assert "id" in data
        assert data["category"] == NarrativeCategory.WEATHER
        assert "muted_at" in data

    def test_missing_category_rejected(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(MUTES_URL, {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_invalid_category_rejected(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(MUTES_URL, {"category": "not-a-category"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_duplicate_mute_rejected_by_serializer(self):
        UserCategoryMute.objects.create(account=self.user, category=NarrativeCategory.WEATHER)
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            MUTES_URL, {"category": NarrativeCategory.WEATHER}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class UserCategoryMuteDeleteTest(APITestCase):
    """DELETE /api/narrative/category-mutes/{id}/ — unmute."""

    @classmethod
    def setUpTestData(cls):
        cls.user = AccountFactory()
        cls.other = AccountFactory()

    def setUp(self):
        self.mute = UserCategoryMute.objects.create(
            account=self.user, category=NarrativeCategory.WEATHER
        )

    def _url(self):
        return f"{MUTES_URL}{self.mute.pk}/"

    def test_owner_can_delete(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.delete(self._url())
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not UserCategoryMute.objects.filter(pk=self.mute.pk).exists()

    @suppress_permission_errors
    def test_non_owner_rejected(self):
        self.client.force_authenticate(user=self.other)
        response = self.client.delete(self._url())
        assert response.status_code in (
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        )
