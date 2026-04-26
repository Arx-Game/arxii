"""Tests for EpisodeProgressionRequirementViewSet — Phase 4 Wave 9.

Covers:
  GET  /api/episode-progression-requirements/          — list (filtered by episode)
  POST /api/episode-progression-requirements/          — create (Lead GM happy path + 403)
  PATCH /api/episode-progression-requirements/{id}/    — update (Lead GM gate)
  DELETE /api/episode-progression-requirements/{id}/   — delete (Lead GM ok, player 403)
"""

import json

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core_management.test_utils import suppress_permission_errors
from evennia_extensions.factories import AccountFactory
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.stories.constants import BeatOutcome
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    EpisodeProgressionRequirementFactory,
    StoryFactory,
)
from world.stories.models import EpisodeProgressionRequirement


class EpisodeProgressionRequirementViewSetTest(APITestCase):
    """Tests for EpisodeProgressionRequirementViewSet CRUD."""

    @classmethod
    def setUpTestData(cls):
        cls.lead_gm_account = AccountFactory()
        cls.lead_gm_profile = GMProfileFactory(account=cls.lead_gm_account)
        cls.gm_table = GMTableFactory(gm=cls.lead_gm_profile)

        cls.staff_account = AccountFactory(is_staff=True)
        cls.player_account = AccountFactory()

        cls.story = StoryFactory(
            owners=[cls.lead_gm_account],
            primary_table=cls.gm_table,
        )
        cls.chapter = ChapterFactory(story=cls.story)
        cls.episode = EpisodeFactory(chapter=cls.chapter, order=1)
        cls.beat = BeatFactory(episode=cls.episode)

        # Pre-existing requirement
        cls.requirement = EpisodeProgressionRequirementFactory(
            episode=cls.episode,
            beat=cls.beat,
            required_outcome=BeatOutcome.SUCCESS,
        )

        # Second beat for create tests (different beat to avoid unique constraint)
        cls.beat2 = BeatFactory(episode=cls.episode)

        # Unrelated story/episode for isolation
        cls.other_story = StoryFactory()
        cls.other_chapter = ChapterFactory(story=cls.other_story)
        cls.other_episode = EpisodeFactory(chapter=cls.other_chapter)
        cls.other_beat = BeatFactory(episode=cls.other_episode)
        cls.other_requirement = EpisodeProgressionRequirementFactory(
            episode=cls.other_episode,
            beat=cls.other_beat,
        )

    def test_list_returns_all_for_authenticated_user(self):
        """Authenticated user can list requirements."""
        self.client.force_authenticate(user=self.player_account)
        url = reverse("episodeprogressionrequirement-list")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK

    def test_list_filtered_by_episode(self):
        """Filtering by episode returns only matching requirements."""
        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("episodeprogressionrequirement-list")
        response = self.client.get(url, {"episode": self.episode.pk})
        assert response.status_code == status.HTTP_200_OK
        pks = [item["id"] for item in response.data["results"]]
        assert self.requirement.pk in pks
        assert self.other_requirement.pk not in pks

    def test_retrieve_requirement(self):
        """Can retrieve a specific requirement."""
        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("episodeprogressionrequirement-detail", kwargs={"pk": self.requirement.pk})
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["episode"] == self.episode.pk
        assert response.data["beat"] == self.beat.pk
        assert response.data["required_outcome"] == BeatOutcome.SUCCESS

    def test_create_requirement_lead_gm_happy_path(self):
        """Lead GM can create a progression requirement."""
        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("episodeprogressionrequirement-list")
        data = {
            "episode": self.episode.pk,
            "beat": self.beat2.pk,
            "required_outcome": BeatOutcome.FAILURE,
        }
        response = self.client.post(url, json.dumps(data), content_type="application/json")
        assert response.status_code == status.HTTP_201_CREATED
        assert EpisodeProgressionRequirement.objects.filter(
            episode=self.episode,
            beat=self.beat2,
            required_outcome=BeatOutcome.FAILURE,
        ).exists()

    @suppress_permission_errors
    def test_create_requirement_denied_for_player(self):
        """Player cannot create a requirement."""
        self.client.force_authenticate(user=self.player_account)
        url = reverse("episodeprogressionrequirement-list")
        data = {
            "episode": self.episode.pk,
            "beat": self.beat2.pk,
            "required_outcome": BeatOutcome.SUCCESS,
        }
        response = self.client.post(url, json.dumps(data), content_type="application/json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_requirement_lead_gm(self):
        """Lead GM can update a requirement's required_outcome."""
        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("episodeprogressionrequirement-detail", kwargs={"pk": self.requirement.pk})
        response = self.client.patch(
            url,
            json.dumps({"required_outcome": BeatOutcome.FAILURE}),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_200_OK
        self.requirement.refresh_from_db()
        assert self.requirement.required_outcome == BeatOutcome.FAILURE
        # Restore for other tests
        self.requirement.required_outcome = BeatOutcome.SUCCESS
        self.requirement.save(update_fields=["required_outcome"])

    @suppress_permission_errors
    def test_update_requirement_denied_for_player(self):
        """Player cannot update a requirement."""
        self.client.force_authenticate(user=self.player_account)
        url = reverse("episodeprogressionrequirement-detail", kwargs={"pk": self.requirement.pk})
        response = self.client.patch(
            url,
            json.dumps({"required_outcome": BeatOutcome.FAILURE}),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_delete_requirement_lead_gm(self):
        """Lead GM can delete a requirement."""
        to_delete = EpisodeProgressionRequirementFactory(
            episode=self.episode,
            beat=BeatFactory(episode=self.episode),
        )
        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("episodeprogressionrequirement-detail", kwargs={"pk": to_delete.pk})
        response = self.client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not EpisodeProgressionRequirement.objects.filter(pk=to_delete.pk).exists()

    @suppress_permission_errors
    def test_delete_requirement_denied_for_player(self):
        """Player cannot delete a requirement."""
        self.client.force_authenticate(user=self.player_account)
        url = reverse("episodeprogressionrequirement-detail", kwargs={"pk": self.requirement.pk})
        response = self.client.delete(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_staff_can_create_requirement(self):
        """Staff can create a requirement regardless of story ownership."""
        self.client.force_authenticate(user=self.staff_account)
        url = reverse("episodeprogressionrequirement-list")
        beat3 = BeatFactory(episode=self.episode)
        data = {
            "episode": self.episode.pk,
            "beat": beat3.pk,
            "required_outcome": BeatOutcome.SUCCESS,
        }
        response = self.client.post(url, json.dumps(data), content_type="application/json")
        assert response.status_code == status.HTTP_201_CREATED

    def test_unauthenticated_list_denied(self):
        """Unauthenticated requests are rejected."""
        url = reverse("episodeprogressionrequirement-list")
        response = self.client.get(url)
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )
