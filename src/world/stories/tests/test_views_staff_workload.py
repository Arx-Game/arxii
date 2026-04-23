"""Tests for StaffWorkloadView — GET /api/stories/staff-workload/.

Scenarios:
- Unauthenticated → 401/403.
- Authenticated non-staff → 403.
- Staff → 200 with all expected top-level keys.
- Stale stories (last_advanced_at older than STALE_STORY_DAYS) appear in stale_stories.
- Recent stories do not appear in stale_stories.
- Stories with current_episode=None appear in stories_at_frontier.
- Stories with a current_episode do not appear in stories_at_frontier.
- counts_by_scope reflects total story counts.
- pending_agm_claims_count reflects open AGM claims.
- open_session_requests_count reflects open SessionRequests.
"""

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from core_management.test_utils import suppress_permission_errors
from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.stories.constants import AssistantClaimStatus, SessionRequestStatus, StoryScope
from world.stories.factories import (
    AssistantGMClaimFactory,
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    SessionRequestFactory,
    StoryFactory,
    StoryProgressFactory,
)
from world.stories.services.dashboards import STALE_STORY_DAYS

STAFF_WORKLOAD_URL = reverse("stories-staff-workload")


class StaffWorkloadAuthTest(APITestCase):
    """Authentication and staff permission gate."""

    @suppress_permission_errors
    def test_unauthenticated_rejected(self):
        response = self.client.get(STAFF_WORKLOAD_URL)
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    @suppress_permission_errors
    def test_non_staff_rejected(self):
        user = AccountFactory()
        self.client.force_authenticate(user=user)
        response = self.client.get(STAFF_WORKLOAD_URL)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_staff_gets_200(self):
        staff = AccountFactory(is_staff=True)
        self.client.force_authenticate(user=staff)
        response = self.client.get(STAFF_WORKLOAD_URL)
        assert response.status_code == status.HTTP_200_OK


class StaffWorkloadResponseShapeTest(APITestCase):
    """Response contains all expected top-level keys."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)

    def test_response_has_all_keys(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(STAFF_WORKLOAD_URL)
        assert response.status_code == status.HTTP_200_OK
        for key in [
            "per_gm_queue_depth",
            "stale_stories",
            "stories_at_frontier",
            "pending_agm_claims_count",
            "open_session_requests_count",
            "counts_by_scope",
        ]:
            assert key in response.data, f"Missing key: {key}"


class StaffWorkloadStaleStoriesTest(APITestCase):
    """Stale stories detection."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)

        cls.sheet = CharacterSheetFactory()
        cls.story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=cls.sheet)
        cls.recent_story = StoryFactory(scope=StoryScope.CHARACTER)
        cls.recent_sheet = CharacterSheetFactory()
        cls.recent_story.character_sheet = cls.recent_sheet
        cls.recent_story.save()

        # Stale progress: last_advanced_at is older than threshold.
        cls.stale_progress = StoryProgressFactory(
            story=cls.story,
            character_sheet=cls.sheet,
            is_active=True,
        )
        # Force last_advanced_at to be stale.
        stale_time = timezone.now() - timedelta(days=STALE_STORY_DAYS + 1)
        StoryProgressFactory._meta.model.objects.filter(pk=cls.stale_progress.pk).update(
            last_advanced_at=stale_time
        )

        # Recent progress: last_advanced_at is fresh (created now by factory).
        cls.recent_progress = StoryProgressFactory(
            story=cls.recent_story,
            character_sheet=cls.recent_sheet,
            is_active=True,
        )

    def test_stale_story_appears(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(STAFF_WORKLOAD_URL)
        stale = response.data["stale_stories"]
        stale_story_ids = [s["story_id"] for s in stale]
        assert self.story.pk in stale_story_ids

    def test_recent_story_not_in_stale(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(STAFF_WORKLOAD_URL)
        stale = response.data["stale_stories"]
        stale_story_ids = [s["story_id"] for s in stale]
        assert self.recent_story.pk not in stale_story_ids

    def test_stale_story_entry_shape(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(STAFF_WORKLOAD_URL)
        stale = response.data["stale_stories"]
        matching = [s for s in stale if s["story_id"] == self.story.pk]
        assert len(matching) >= 1
        entry = matching[0]
        for field in ["story_id", "story_title", "last_advanced_at", "days_stale"]:
            assert field in entry, f"Missing field: {field}"
        assert entry["days_stale"] >= STALE_STORY_DAYS


class StaffWorkloadFrontierTest(APITestCase):
    """Stories at frontier (current_episode=None) detection."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)

        cls.sheet = CharacterSheetFactory()
        cls.story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=cls.sheet)
        cls.chapter = ChapterFactory(story=cls.story, order=1)
        cls.episode = EpisodeFactory(chapter=cls.chapter, order=1)

        cls.frontier_sheet = CharacterSheetFactory()
        cls.frontier_story = StoryFactory(
            scope=StoryScope.CHARACTER, character_sheet=cls.frontier_sheet
        )

        # Progress at frontier (no episode).
        cls.frontier_progress = StoryProgressFactory(
            story=cls.frontier_story,
            character_sheet=cls.frontier_sheet,
            current_episode=None,
            is_active=True,
        )
        # Progress with an episode — should NOT be in frontier list.
        cls.active_progress = StoryProgressFactory(
            story=cls.story,
            character_sheet=cls.sheet,
            current_episode=cls.episode,
            is_active=True,
        )

    def test_frontier_story_appears(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(STAFF_WORKLOAD_URL)
        frontier = response.data["stories_at_frontier"]
        ids = [s["story_id"] for s in frontier]
        assert self.frontier_story.pk in ids

    def test_story_with_episode_not_in_frontier(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(STAFF_WORKLOAD_URL)
        frontier = response.data["stories_at_frontier"]
        ids = [s["story_id"] for s in frontier]
        assert self.story.pk not in ids

    def test_frontier_entry_shape(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(STAFF_WORKLOAD_URL)
        frontier = response.data["stories_at_frontier"]
        matching = [s for s in frontier if s["story_id"] == self.frontier_story.pk]
        assert len(matching) >= 1
        entry = matching[0]
        for field in ["story_id", "story_title", "scope"]:
            assert field in entry, f"Missing field: {field}"


class StaffWorkloadCountsTest(APITestCase):
    """Aggregate count fields."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)

        # Pending AGM claim.
        cls.beat = BeatFactory(agm_eligible=True)
        cls.claim = AssistantGMClaimFactory(beat=cls.beat, status=AssistantClaimStatus.REQUESTED)

        # Open SessionRequest.
        cls.session_req = SessionRequestFactory(status=SessionRequestStatus.OPEN)

    def test_pending_agm_claims_count(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(STAFF_WORKLOAD_URL)
        # At least one claim is pending (our factory-created one).
        assert response.data["pending_agm_claims_count"] >= 1

    def test_open_session_requests_count(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(STAFF_WORKLOAD_URL)
        # At least one session request is open.
        assert response.data["open_session_requests_count"] >= 1

    def test_counts_by_scope_present(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(STAFF_WORKLOAD_URL)
        counts = response.data["counts_by_scope"]
        assert isinstance(counts, dict)
        # All values are non-negative integers.
        for scope, count in counts.items():
            assert isinstance(count, int), f"Non-integer count for scope {scope}"
            assert count >= 0


class StaffWorkloadPerGMQueueTest(APITestCase):
    """per_gm_queue_depth entries shape."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.gm_account = AccountFactory()
        cls.gm_profile = GMProfileFactory(account=cls.gm_account)
        cls.gm_table = GMTableFactory(gm=cls.gm_profile)

        cls.char_sheet = CharacterSheetFactory()
        cls.story = StoryFactory(
            scope=StoryScope.CHARACTER,
            character_sheet=cls.char_sheet,
            primary_table=cls.gm_table,
        )

    def test_per_gm_entry_shape(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(STAFF_WORKLOAD_URL)
        queue = response.data["per_gm_queue_depth"]
        # At least our GM should be there (has a primary story).
        matching = [e for e in queue if e["gm_profile_id"] == self.gm_profile.pk]
        assert len(matching) >= 1
        entry = matching[0]
        for field in ["gm_profile_id", "gm_name", "episodes_ready", "pending_claims"]:
            assert field in entry, f"Missing field: {field}"
        assert isinstance(entry["episodes_ready"], int)
        assert isinstance(entry["pending_claims"], int)
