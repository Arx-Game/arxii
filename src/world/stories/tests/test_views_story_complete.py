"""Tests for StoryViewSet.complete — POST /api/stories/{id}/complete/.

Exposes complete_story via the strict 3-layer pattern: IsLeadGMOnStoryOrStaff
gates access, the service does the atomic work (no input body).
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core_management.test_utils import suppress_permission_errors
from evennia_extensions.factories import AccountFactory
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.stories.factories import StoryFactory
from world.stories.types import StoryStatus


class StoryCompleteViewSetTest(APITestCase):
    """Tests for POST /api/stories/{id}/complete/."""

    @classmethod
    def setUpTestData(cls):
        cls.lead_gm_account = AccountFactory()
        cls.lead_gm_profile = GMProfileFactory(account=cls.lead_gm_account)
        cls.gm_table = GMTableFactory(gm=cls.lead_gm_profile)
        cls.staff_account = AccountFactory(is_staff=True)
        cls.unrelated_account = AccountFactory()

    def _active_story(self):
        return StoryFactory(
            owners=[self.lead_gm_account],
            primary_table=self.gm_table,
            status=StoryStatus.ACTIVE,
        )

    def test_lead_gm_can_complete(self):
        story = self._active_story()
        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("story-complete", kwargs={"pk": story.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        story.refresh_from_db()
        self.assertEqual(story.status, StoryStatus.COMPLETED)
        self.assertIsNotNone(story.completed_at)

    def test_staff_can_complete(self):
        story = self._active_story()
        self.client.force_authenticate(user=self.staff_account)
        url = reverse("story-complete", kwargs={"pk": story.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        story.refresh_from_db()
        self.assertEqual(story.status, StoryStatus.COMPLETED)

    @suppress_permission_errors
    def test_unrelated_user_forbidden(self):
        story = self._active_story()
        self.client.force_authenticate(user=self.unrelated_account)
        url = reverse("story-complete", kwargs={"pk": story.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        story.refresh_from_db()
        self.assertEqual(story.status, StoryStatus.ACTIVE)
