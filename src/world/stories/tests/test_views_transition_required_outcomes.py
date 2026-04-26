"""Tests for TransitionRequiredOutcomeViewSet — Phase 4 Wave 9.

Covers:
  GET  /api/transition-required-outcomes/          — list (filtered by transition)
  POST /api/transition-required-outcomes/          — create (Lead GM happy path + 403)
  PATCH /api/transition-required-outcomes/{id}/    — update (Lead GM gate)
  DELETE /api/transition-required-outcomes/{id}/   — delete (Lead GM ok, player 403)
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
    StoryFactory,
    TransitionFactory,
    TransitionRequiredOutcomeFactory,
)
from world.stories.models import TransitionRequiredOutcome


class TransitionRequiredOutcomeViewSetTest(APITestCase):
    """Tests for TransitionRequiredOutcomeViewSet CRUD."""

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
        cls.ep1 = EpisodeFactory(chapter=cls.chapter, order=1)
        cls.ep2 = EpisodeFactory(chapter=cls.chapter, order=2)

        cls.transition = TransitionFactory(
            source_episode=cls.ep1,
            target_episode=cls.ep2,
        )
        cls.beat = BeatFactory(episode=cls.ep1)
        cls.required_outcome = TransitionRequiredOutcomeFactory(
            transition=cls.transition,
            beat=cls.beat,
            required_outcome=BeatOutcome.SUCCESS,
        )

        # Second beat for create tests (avoids unique constraint on transition+beat)
        cls.beat2 = BeatFactory(episode=cls.ep1)

        # Unrelated story/transition for isolation
        cls.other_story = StoryFactory()
        cls.other_chapter = ChapterFactory(story=cls.other_story)
        cls.other_ep1 = EpisodeFactory(chapter=cls.other_chapter, order=1)
        cls.other_ep2 = EpisodeFactory(chapter=cls.other_chapter, order=2)
        cls.other_transition = TransitionFactory(
            source_episode=cls.other_ep1,
            target_episode=cls.other_ep2,
        )
        cls.other_beat = BeatFactory(episode=cls.other_ep1)
        cls.other_required_outcome = TransitionRequiredOutcomeFactory(
            transition=cls.other_transition,
            beat=cls.other_beat,
        )

    def test_list_returns_all_for_authenticated_user(self):
        """Authenticated user can list required outcomes."""
        self.client.force_authenticate(user=self.player_account)
        url = reverse("transitionrequiredoutcome-list")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK

    def test_list_filtered_by_transition(self):
        """Filtering by transition returns only matching required outcomes."""
        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("transitionrequiredoutcome-list")
        response = self.client.get(url, {"transition": self.transition.pk})
        assert response.status_code == status.HTTP_200_OK
        pks = [item["id"] for item in response.data["results"]]
        assert self.required_outcome.pk in pks
        assert self.other_required_outcome.pk not in pks

    def test_retrieve_required_outcome(self):
        """Can retrieve a specific required outcome."""
        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("transitionrequiredoutcome-detail", kwargs={"pk": self.required_outcome.pk})
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["transition"] == self.transition.pk
        assert response.data["beat"] == self.beat.pk
        assert response.data["required_outcome"] == BeatOutcome.SUCCESS

    def test_create_required_outcome_lead_gm_happy_path(self):
        """Lead GM can create a required outcome."""
        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("transitionrequiredoutcome-list")
        data = {
            "transition": self.transition.pk,
            "beat": self.beat2.pk,
            "required_outcome": BeatOutcome.FAILURE,
        }
        response = self.client.post(url, json.dumps(data), content_type="application/json")
        assert response.status_code == status.HTTP_201_CREATED
        assert TransitionRequiredOutcome.objects.filter(
            transition=self.transition,
            beat=self.beat2,
            required_outcome=BeatOutcome.FAILURE,
        ).exists()

    @suppress_permission_errors
    def test_create_required_outcome_denied_for_player(self):
        """Player cannot create a required outcome."""
        self.client.force_authenticate(user=self.player_account)
        url = reverse("transitionrequiredoutcome-list")
        data = {
            "transition": self.transition.pk,
            "beat": self.beat2.pk,
            "required_outcome": BeatOutcome.SUCCESS,
        }
        response = self.client.post(url, json.dumps(data), content_type="application/json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_required_outcome_lead_gm(self):
        """Lead GM can update a required outcome."""
        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("transitionrequiredoutcome-detail", kwargs={"pk": self.required_outcome.pk})
        response = self.client.patch(
            url,
            json.dumps({"required_outcome": BeatOutcome.FAILURE}),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_200_OK
        self.required_outcome.refresh_from_db()
        assert self.required_outcome.required_outcome == BeatOutcome.FAILURE
        # Restore for other tests
        self.required_outcome.required_outcome = BeatOutcome.SUCCESS
        self.required_outcome.save(update_fields=["required_outcome"])

    @suppress_permission_errors
    def test_update_required_outcome_denied_for_player(self):
        """Player cannot update a required outcome."""
        self.client.force_authenticate(user=self.player_account)
        url = reverse("transitionrequiredoutcome-detail", kwargs={"pk": self.required_outcome.pk})
        response = self.client.patch(
            url,
            json.dumps({"required_outcome": BeatOutcome.FAILURE}),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_delete_required_outcome_lead_gm(self):
        """Lead GM can delete a required outcome."""
        to_delete = TransitionRequiredOutcomeFactory(
            transition=self.transition,
            beat=BeatFactory(episode=self.ep1),
        )
        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("transitionrequiredoutcome-detail", kwargs={"pk": to_delete.pk})
        response = self.client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not TransitionRequiredOutcome.objects.filter(pk=to_delete.pk).exists()

    @suppress_permission_errors
    def test_delete_required_outcome_denied_for_player(self):
        """Player cannot delete a required outcome."""
        self.client.force_authenticate(user=self.player_account)
        url = reverse("transitionrequiredoutcome-detail", kwargs={"pk": self.required_outcome.pk})
        response = self.client.delete(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_staff_can_create_required_outcome(self):
        """Staff can create a required outcome regardless of story ownership."""
        self.client.force_authenticate(user=self.staff_account)
        url = reverse("transitionrequiredoutcome-list")
        beat3 = BeatFactory(episode=self.ep1)
        data = {
            "transition": self.transition.pk,
            "beat": beat3.pk,
            "required_outcome": BeatOutcome.SUCCESS,
        }
        response = self.client.post(url, json.dumps(data), content_type="application/json")
        assert response.status_code == status.HTTP_201_CREATED

    def test_unauthenticated_list_denied(self):
        """Unauthenticated requests are rejected."""
        url = reverse("transitionrequiredoutcome-list")
        response = self.client.get(url)
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )
