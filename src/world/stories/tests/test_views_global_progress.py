"""Tests for GlobalStoryProgressViewSet — permission matrix, CRUD, filters."""

import json

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core_management.test_utils import suppress_permission_errors
from evennia_extensions.factories import AccountFactory
from world.stories.constants import StoryScope
from world.stories.factories import GlobalStoryProgressFactory, StoryFactory


class GlobalStoryProgressViewSetPermissionTest(APITestCase):
    """Test the GlobalStoryProgressViewSet permission matrix."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.regular_user = AccountFactory()
        cls.other_user = AccountFactory()

        cls.story = StoryFactory(scope=StoryScope.GLOBAL)
        cls.progress = GlobalStoryProgressFactory(story=cls.story)

    # ---------- list --------------------------------------------------------

    def test_authenticated_user_can_list(self):
        """Any authenticated user can list global progress (metaplot is public)."""
        self.client.force_authenticate(user=self.regular_user)
        url = reverse("globalstoryprogress-list")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK

    def test_staff_can_list(self):
        """Staff can list global progress."""
        self.client.force_authenticate(user=self.staff)
        url = reverse("globalstoryprogress-list")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK

    @suppress_permission_errors
    def test_unauthenticated_cannot_list(self):
        """Unauthenticated requests are rejected."""
        url = reverse("globalstoryprogress-list")
        response = self.client.get(url)
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    # ---------- retrieve ----------------------------------------------------

    def test_regular_user_can_retrieve(self):
        """Any authenticated user can retrieve a global progress record."""
        self.client.force_authenticate(user=self.regular_user)
        url = reverse("globalstoryprogress-detail", kwargs={"pk": self.progress.pk})
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == self.progress.id

    # ---------- create -------------------------------------------------------

    def test_staff_can_create(self):
        """Staff can create a global progress record."""
        new_story = StoryFactory(scope=StoryScope.GLOBAL)
        self.client.force_authenticate(user=self.staff)
        url = reverse("globalstoryprogress-list")
        data = {"story": new_story.id, "is_active": True}
        response = self.client.post(url, json.dumps(data), content_type="application/json")
        assert response.status_code == status.HTTP_201_CREATED

    @suppress_permission_errors
    def test_regular_user_cannot_create(self):
        """Non-staff users cannot create global progress records."""
        new_story = StoryFactory(scope=StoryScope.GLOBAL)
        self.client.force_authenticate(user=self.regular_user)
        url = reverse("globalstoryprogress-list")
        data = {"story": new_story.id, "is_active": True}
        response = self.client.post(url, json.dumps(data), content_type="application/json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    # ---------- update -------------------------------------------------------

    def test_staff_can_update(self):
        """Staff can update a global progress record."""
        self.client.force_authenticate(user=self.staff)
        url = reverse("globalstoryprogress-detail", kwargs={"pk": self.progress.pk})
        data = {"is_active": False}
        response = self.client.patch(url, json.dumps(data), content_type="application/json")
        assert response.status_code == status.HTTP_200_OK

    @suppress_permission_errors
    def test_regular_user_cannot_update(self):
        """Non-staff users cannot update global progress records."""
        self.client.force_authenticate(user=self.regular_user)
        url = reverse("globalstoryprogress-detail", kwargs={"pk": self.progress.pk})
        data = {"is_active": False}
        response = self.client.patch(url, json.dumps(data), content_type="application/json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    # ---------- delete -------------------------------------------------------

    @suppress_permission_errors
    def test_regular_user_cannot_delete(self):
        """Non-staff users cannot delete global progress records."""
        self.client.force_authenticate(user=self.regular_user)
        url = reverse("globalstoryprogress-detail", kwargs={"pk": self.progress.pk})
        response = self.client.delete(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    # ---------- filters ------------------------------------------------------

    def test_filter_by_story(self):
        """Filter by story ID returns only matching records."""
        other_story = StoryFactory(scope=StoryScope.GLOBAL)
        GlobalStoryProgressFactory(story=other_story)

        self.client.force_authenticate(user=self.staff)
        url = reverse("globalstoryprogress-list")
        response = self.client.get(url, {"story": self.story.id})
        assert response.status_code == status.HTTP_200_OK
        ids = [r["id"] for r in response.data["results"]]
        assert self.progress.id in ids
        for r_id in ids:
            assert r_id == self.progress.id

    def test_filter_by_is_active_true(self):
        """Filter is_active=true returns only active records."""
        self.client.force_authenticate(user=self.staff)
        url = reverse("globalstoryprogress-list")
        response = self.client.get(url, {"is_active": "true"})
        assert response.status_code == status.HTTP_200_OK
        for r in response.data["results"]:
            assert r["is_active"] is True

    # ---------- validation ---------------------------------------------------

    @suppress_permission_errors
    def test_create_rejects_non_global_scope_story(self):
        """Creating with a GROUP-scope story returns 400."""
        group_story = StoryFactory(scope=StoryScope.GROUP)
        self.client.force_authenticate(user=self.staff)
        url = reverse("globalstoryprogress-list")
        data = {"story": group_story.id, "is_active": True}
        response = self.client.post(url, json.dumps(data), content_type="application/json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_serializer_fields_present(self):
        """Serialized response contains all expected fields."""
        self.client.force_authenticate(user=self.staff)
        url = reverse("globalstoryprogress-detail", kwargs={"pk": self.progress.pk})
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        for field in [
            "id",
            "story",
            "current_episode",
            "started_at",
            "last_advanced_at",
            "is_active",
        ]:
            assert field in response.data, f"Missing field: {field}"
