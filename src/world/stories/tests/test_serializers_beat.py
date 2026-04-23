"""Tests for BeatSerializer — Phase 2 predicate config fields and clean() mirroring."""

import json

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core_management.test_utils import suppress_permission_errors
from evennia_extensions.factories import AccountFactory
from world.stories.constants import (
    BeatOutcome,
    BeatPredicateType,
    BeatVisibility,
)
from world.stories.factories import BeatFactory, ChapterFactory, EpisodeFactory, StoryFactory


class BeatSerializerFieldsTest(APITestCase):
    """All Phase 2 predicate config fields appear in the serialized output."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.story = StoryFactory(owners=[cls.staff])
        cls.chapter = ChapterFactory(story=cls.story)
        cls.episode = EpisodeFactory(chapter=cls.chapter)
        cls.beat = BeatFactory(
            episode=cls.episode,
            predicate_type=BeatPredicateType.GM_MARKED,
        )

    def test_all_phase2_fields_present_in_response(self):
        """GET /api/beats/{pk}/ includes all Phase 2 predicate config fields."""
        self.client.force_authenticate(user=self.staff)
        url = reverse("beat-detail", kwargs={"pk": self.beat.pk})
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        for field in [
            "id",
            "episode",
            "predicate_type",
            "outcome",
            "visibility",
            "internal_description",
            "player_hint",
            "player_resolution_text",
            "order",
            "required_level",
            "required_achievement",
            "required_condition_template",
            "required_codex_entry",
            "referenced_story",
            "referenced_milestone_type",
            "referenced_chapter",
            "referenced_episode",
            "required_points",
            "agm_eligible",
            "deadline",
            "created_at",
            "updated_at",
        ]:
            assert field in response.data, f"Missing field: {field}"


class BeatSerializerCreateValidationTest(APITestCase):
    """BeatSerializer.validate() mirrors Beat.clean() for predicate-type invariants."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.story = StoryFactory(owners=[cls.staff])
        cls.chapter = ChapterFactory(story=cls.story)
        cls.episode = EpisodeFactory(chapter=cls.chapter)

    def _post_beat(self, data: dict) -> object:
        self.client.force_authenticate(user=self.staff)
        return self.client.post(
            reverse("beat-list"),
            json.dumps(data),
            content_type="application/json",
        )

    def _base_beat_data(self) -> dict:
        return {
            "episode": self.episode.id,
            "predicate_type": BeatPredicateType.GM_MARKED,
            "outcome": BeatOutcome.UNSATISFIED,
            "visibility": BeatVisibility.HINTED,
            "internal_description": "Test beat description",
            "order": 1,
        }

    # ---------- happy paths -------------------------------------------------

    def test_gm_marked_beat_creates_successfully(self):
        """GM_MARKED beat with no config fields is accepted."""
        response = self._post_beat(self._base_beat_data())
        assert response.status_code == status.HTTP_201_CREATED

    def test_character_level_beat_creates_successfully(self):
        """CHARACTER_LEVEL_AT_LEAST beat with required_level is accepted."""
        data = {
            **self._base_beat_data(),
            "predicate_type": BeatPredicateType.CHARACTER_LEVEL_AT_LEAST,
            "required_level": 5,
        }
        response = self._post_beat(data)
        assert response.status_code == status.HTTP_201_CREATED

    def test_aggregate_threshold_beat_creates_successfully(self):
        """AGGREGATE_THRESHOLD beat with required_points is accepted."""
        data = {
            **self._base_beat_data(),
            "predicate_type": BeatPredicateType.AGGREGATE_THRESHOLD,
            "required_points": 100,
        }
        response = self._post_beat(data)
        assert response.status_code == status.HTTP_201_CREATED

    # ---------- missing required config -------------------------------------

    @suppress_permission_errors
    def test_character_level_without_required_level_rejected(self):
        """CHARACTER_LEVEL_AT_LEAST without required_level returns 400."""
        data = {
            **self._base_beat_data(),
            "predicate_type": BeatPredicateType.CHARACTER_LEVEL_AT_LEAST,
            # required_level intentionally omitted
        }
        response = self._post_beat(data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @suppress_permission_errors
    def test_aggregate_threshold_without_required_points_rejected(self):
        """AGGREGATE_THRESHOLD without required_points returns 400."""
        data = {
            **self._base_beat_data(),
            "predicate_type": BeatPredicateType.AGGREGATE_THRESHOLD,
            # required_points intentionally omitted
        }
        response = self._post_beat(data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    # ---------- extra config forbidden for type -----------------------------

    @suppress_permission_errors
    def test_gm_marked_with_required_level_rejected(self):
        """GM_MARKED beat with required_level (wrong for type) returns 400."""
        data = {
            **self._base_beat_data(),
            "predicate_type": BeatPredicateType.GM_MARKED,
            "required_level": 3,  # not valid for GM_MARKED
        }
        response = self._post_beat(data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @suppress_permission_errors
    def test_character_level_with_required_points_rejected(self):
        """CHARACTER_LEVEL_AT_LEAST with required_points (wrong type) returns 400."""
        data = {
            **self._base_beat_data(),
            "predicate_type": BeatPredicateType.CHARACTER_LEVEL_AT_LEAST,
            "required_level": 5,
            "required_points": 100,  # belongs to AGGREGATE_THRESHOLD only
        }
        response = self._post_beat(data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    # ---------- partial update validation -----------------------------------

    def test_partial_update_preserves_existing_config(self):
        """PATCH with only visibility doesn't wipe required config fields."""
        beat = BeatFactory(
            episode=self.episode,
            predicate_type=BeatPredicateType.CHARACTER_LEVEL_AT_LEAST,
            required_level=5,
        )
        self.client.force_authenticate(user=self.staff)
        url = reverse("beat-detail", kwargs={"pk": beat.pk})
        response = self.client.patch(
            url,
            json.dumps({"visibility": BeatVisibility.VISIBLE}),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["required_level"] == 5
        assert response.data["predicate_type"] == BeatPredicateType.CHARACTER_LEVEL_AT_LEAST

    @suppress_permission_errors
    def test_partial_update_changing_type_without_config_rejected(self):
        """PATCH switching predicate_type to one that needs config returns 400
        when required config is not also provided.
        """
        beat = BeatFactory(
            episode=self.episode,
            predicate_type=BeatPredicateType.GM_MARKED,
        )
        self.client.force_authenticate(user=self.staff)
        url = reverse("beat-detail", kwargs={"pk": beat.pk})
        response = self.client.patch(
            url,
            json.dumps({"predicate_type": BeatPredicateType.CHARACTER_LEVEL_AT_LEAST}),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_partial_update_changing_type_with_config_accepted(self):
        """PATCH switching predicate_type AND providing the required config is accepted."""
        beat = BeatFactory(
            episode=self.episode,
            predicate_type=BeatPredicateType.GM_MARKED,
        )
        self.client.force_authenticate(user=self.staff)
        url = reverse("beat-detail", kwargs={"pk": beat.pk})
        response = self.client.patch(
            url,
            json.dumps(
                {
                    "predicate_type": BeatPredicateType.CHARACTER_LEVEL_AT_LEAST,
                    "required_level": 10,
                }
            ),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["required_level"] == 10


class BeatViewSetPermissionsTest(APITestCase):
    """BeatViewSet uses IsEpisodeStoryOwnerOrStaff permission — spot-check."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = AccountFactory()
        cls.non_owner = AccountFactory()
        cls.staff = AccountFactory(is_staff=True)

        cls.story = StoryFactory(owners=[cls.owner])
        cls.chapter = ChapterFactory(story=cls.story)
        cls.episode = EpisodeFactory(chapter=cls.chapter)
        cls.beat = BeatFactory(episode=cls.episode)

    def test_staff_can_retrieve(self):
        self.client.force_authenticate(user=self.staff)
        url = reverse("beat-detail", kwargs={"pk": self.beat.pk})
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK

    def test_story_owner_can_retrieve(self):
        self.client.force_authenticate(user=self.owner)
        url = reverse("beat-detail", kwargs={"pk": self.beat.pk})
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK

    def test_authenticated_can_list(self):
        """list is allowed for any authenticated user (object-level enforced on retrieve)."""
        self.client.force_authenticate(user=self.non_owner)
        response = self.client.get(reverse("beat-list"))
        assert response.status_code == status.HTTP_200_OK

    @suppress_permission_errors
    def test_non_owner_cannot_update(self):
        """Non-owner cannot update a beat."""
        self.client.force_authenticate(user=self.non_owner)
        url = reverse("beat-detail", kwargs={"pk": self.beat.pk})
        response = self.client.patch(
            url,
            json.dumps({"visibility": BeatVisibility.VISIBLE}),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_story_owner_can_update(self):
        """Story owner can update their beat."""
        self.client.force_authenticate(user=self.owner)
        url = reverse("beat-detail", kwargs={"pk": self.beat.pk})
        response = self.client.patch(
            url,
            json.dumps({"visibility": BeatVisibility.VISIBLE}),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_200_OK

    def test_story_owner_can_create_beat(self):
        """Story owner can create a beat for their episode."""
        self.client.force_authenticate(user=self.owner)
        data = {
            "episode": self.episode.id,
            "predicate_type": BeatPredicateType.GM_MARKED,
            "outcome": BeatOutcome.UNSATISFIED,
            "visibility": BeatVisibility.HINTED,
            "internal_description": "A new beat",
            "order": 99,
        }
        response = self.client.post(
            reverse("beat-list"),
            json.dumps(data),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_201_CREATED
