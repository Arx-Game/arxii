"""Tests for TransitionViewSet — Phase 4 Wave 9.

Covers:
  GET  /api/transitions/          — list (filtered by source_episode)
  POST /api/transitions/          — create (Lead GM happy path + 403 for player)
  PATCH /api/transitions/{id}/    — update (Lead GM gate)
  DELETE /api/transitions/{id}/   — delete (Lead GM ok, player 403)
"""

import json

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core_management.test_utils import suppress_permission_errors
from evennia_extensions.factories import AccountFactory
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.stories.constants import TransitionMode
from world.stories.factories import (
    ChapterFactory,
    EpisodeFactory,
    StoryFactory,
    TransitionFactory,
)
from world.stories.models import Transition


class TransitionViewSetTest(APITestCase):
    """Tests for GET /api/transitions/ and related CRUD."""

    @classmethod
    def setUpTestData(cls):
        # Lead GM setup
        cls.lead_gm_account = AccountFactory()
        cls.lead_gm_profile = GMProfileFactory(account=cls.lead_gm_account)
        cls.gm_table = GMTableFactory(gm=cls.lead_gm_profile)

        cls.staff_account = AccountFactory(is_staff=True)
        cls.player_account = AccountFactory()

        # Story with a chapter and two episodes.
        cls.story = StoryFactory(
            owners=[cls.lead_gm_account],
            primary_table=cls.gm_table,
        )
        cls.chapter = ChapterFactory(story=cls.story)
        cls.ep1 = EpisodeFactory(chapter=cls.chapter, order=1)
        cls.ep2 = EpisodeFactory(chapter=cls.chapter, order=2)
        cls.ep3 = EpisodeFactory(chapter=cls.chapter, order=3)

        # Pre-existing transition from ep1 -> ep2
        cls.transition = TransitionFactory(
            source_episode=cls.ep1,
            target_episode=cls.ep2,
            mode=TransitionMode.AUTO,
        )

        # A separate story (unrelated) with its own episode/transition for isolation tests.
        cls.other_story = StoryFactory()
        cls.other_chapter = ChapterFactory(story=cls.other_story)
        cls.other_ep = EpisodeFactory(chapter=cls.other_chapter, order=1)
        cls.other_ep2 = EpisodeFactory(chapter=cls.other_chapter, order=2)
        cls.other_transition = TransitionFactory(
            source_episode=cls.other_ep,
            target_episode=cls.other_ep2,
        )

    def test_list_returns_all_for_authenticated_user(self):
        """Authenticated user can list transitions."""
        self.client.force_authenticate(user=self.player_account)
        url = reverse("transition-list")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK

    def test_list_filtered_by_source_episode(self):
        """Filtering by source_episode returns only matching transitions."""
        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("transition-list")
        response = self.client.get(url, {"source_episode": self.ep1.pk})
        assert response.status_code == status.HTTP_200_OK
        pks = [item["id"] for item in response.data["results"]]
        assert self.transition.pk in pks
        assert self.other_transition.pk not in pks

    def test_retrieve_returns_breadcrumb_fields(self):
        """Detail response includes source_episode_title and target_episode_title."""
        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("transition-detail", kwargs={"pk": self.transition.pk})
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["source_episode_title"] == self.ep1.title
        assert response.data["target_episode_title"] == self.ep2.title

    def test_retrieve_null_target_returns_none_title(self):
        """A frontier transition (null target) has target_episode_title=None."""
        frontier = TransitionFactory(source_episode=self.ep1, target_episode=None)
        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("transition-detail", kwargs={"pk": frontier.pk})
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["target_episode_title"] is None
        frontier.delete()

    def test_create_transition_lead_gm_happy_path(self):
        """Lead GM can create a transition."""
        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("transition-list")
        data = {
            "source_episode": self.ep1.pk,
            "target_episode": self.ep3.pk,
            "mode": TransitionMode.GM_CHOICE,
            "connection_type": "",
            "connection_summary": "Only if the hero fails.",
            "order": 1,
        }
        response = self.client.post(url, json.dumps(data), content_type="application/json")
        assert response.status_code == status.HTTP_201_CREATED
        assert Transition.objects.filter(source_episode=self.ep1, target_episode=self.ep3).exists()

    @suppress_permission_errors
    def test_create_transition_denied_for_player(self):
        """Non-GM player cannot create a transition."""
        self.client.force_authenticate(user=self.player_account)
        url = reverse("transition-list")
        data = {
            "source_episode": self.ep1.pk,
            "target_episode": self.ep3.pk,
            "mode": TransitionMode.AUTO,
        }
        response = self.client.post(url, json.dumps(data), content_type="application/json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_transition_lead_gm(self):
        """Lead GM can update a transition."""
        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("transition-detail", kwargs={"pk": self.transition.pk})
        response = self.client.patch(
            url,
            json.dumps({"connection_summary": "Updated summary."}),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_200_OK
        self.transition.refresh_from_db()
        assert self.transition.connection_summary == "Updated summary."

    @suppress_permission_errors
    def test_update_transition_denied_for_player(self):
        """Player cannot update a transition."""
        self.client.force_authenticate(user=self.player_account)
        url = reverse("transition-detail", kwargs={"pk": self.transition.pk})
        response = self.client.patch(
            url,
            json.dumps({"connection_summary": "Hacked!"}),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_delete_transition_lead_gm(self):
        """Lead GM can delete a transition they own."""
        to_delete = TransitionFactory(source_episode=self.ep1, target_episode=self.ep2, order=99)
        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("transition-detail", kwargs={"pk": to_delete.pk})
        response = self.client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Transition.objects.filter(pk=to_delete.pk).exists()

    @suppress_permission_errors
    def test_delete_transition_denied_for_player(self):
        """Player cannot delete a transition."""
        self.client.force_authenticate(user=self.player_account)
        url = reverse("transition-detail", kwargs={"pk": self.transition.pk})
        response = self.client.delete(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_staff_can_create_transition(self):
        """Staff can create a transition regardless of story ownership."""
        self.client.force_authenticate(user=self.staff_account)
        url = reverse("transition-list")
        ep4 = EpisodeFactory(chapter=self.chapter, order=4)
        data = {
            "source_episode": ep4.pk,
            "target_episode": self.ep2.pk,
            "mode": TransitionMode.AUTO,
            "connection_type": "",
            "connection_summary": "",
            "order": 0,
        }
        response = self.client.post(url, json.dumps(data), content_type="application/json")
        assert response.status_code == status.HTTP_201_CREATED

    def test_unauthenticated_list_denied(self):
        """Unauthenticated requests are rejected."""
        url = reverse("transition-list")
        response = self.client.get(url)
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )
