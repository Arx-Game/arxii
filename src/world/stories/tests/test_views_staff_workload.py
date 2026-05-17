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
from world.stories.constants import (
    AssistantClaimStatus,
    ProgressStatus,
    SessionRequestStatus,
    StoryScope,
)
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

# Exact query count the bounded implementation issues regardless of how many
# GMs / stories / progress rows exist. The unbounded implementation scaled
# linearly (29 queries at N=3, 38 at N=6 — exactly 3 queries per GM); the
# bounded one issues a flat constant: verified identical (26) at N=6 and
# N=12 with episode-bearing rows that exercise the eligibility batch path.
BOUNDED_QUERY_COUNT = 26


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
            "stories_waiting_for_gm",
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


class StaffWorkloadWaitingForGMTest(APITestCase):
    """WAITING_FOR_GM progress is surfaced with age regardless of staleness."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)

        cls.sheet = CharacterSheetFactory()
        cls.story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=cls.sheet)
        # Fresh (not stale) but waiting on the GM — still a dropped ball.
        cls.waiting_progress = StoryProgressFactory(
            story=cls.story,
            character_sheet=cls.sheet,
            is_active=True,
            status=ProgressStatus.WAITING_FOR_GM,
        )

        cls.active_sheet = CharacterSheetFactory()
        cls.active_story = StoryFactory(
            scope=StoryScope.CHARACTER, character_sheet=cls.active_sheet
        )
        cls.active_progress = StoryProgressFactory(
            story=cls.active_story,
            character_sheet=cls.active_sheet,
            is_active=True,
            status=ProgressStatus.ACTIVE,
        )

    def test_waiting_story_appears(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(STAFF_WORKLOAD_URL)
        waiting = response.data["stories_waiting_for_gm"]
        ids = [w["story_id"] for w in waiting]
        assert self.story.pk in ids

    def test_active_story_not_in_waiting(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(STAFF_WORKLOAD_URL)
        waiting = response.data["stories_waiting_for_gm"]
        ids = [w["story_id"] for w in waiting]
        assert self.active_story.pk not in ids

    def test_waiting_entry_shape_exposes_age(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(STAFF_WORKLOAD_URL)
        waiting = response.data["stories_waiting_for_gm"]
        matching = [w for w in waiting if w["story_id"] == self.story.pk]
        assert len(matching) >= 1
        entry = matching[0]
        for field in ["story_id", "story_title", "scope", "last_advanced_at", "days_waiting"]:
            assert field in entry, f"Missing field: {field}"
        assert entry["last_advanced_at"] is not None
        assert isinstance(entry["days_waiting"], int)
        assert entry["days_waiting"] >= 0


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


def _episode_for(story) -> object:
    """Create a chapter+episode under ``story`` and return the episode."""
    chapter = ChapterFactory(story=story, order=1)
    return EpisodeFactory(chapter=chapter, order=1)


def _build_workload_rows(n: int) -> list:
    """Populate every staff-workload bucket with exactly ``n`` distinct rows.

    Returns the created GMProfile instances. Per iteration:

    - a lead story whose active progress sits on a real episode → drives the
      per-GM queue scan *and* the heavier eligibility batch path;
    - a stale row (old ``last_advanced_at``) on an episode;
    - a waiting-for-GM row on an episode;
    - a frontier row (``current_episode=None``).

    Lead/stale/waiting progress carry an episode so they do NOT also fall
    into the frontier bucket — keeping each bucket's length exactly ``n`` so
    a dropped-rows regression is caught precisely.
    """
    gm_profiles = []
    stale_time = timezone.now() - timedelta(days=STALE_STORY_DAYS + 1)
    for _ in range(n):
        gm_account = AccountFactory()
        gm_profile = GMProfileFactory(account=gm_account)
        gm_table = GMTableFactory(gm=gm_profile)

        # Lead story + active progress on a real episode → per-GM queue scan
        # plus the progression-req / transition eligibility batch path.
        lead_sheet = CharacterSheetFactory()
        lead_story = StoryFactory(
            scope=StoryScope.CHARACTER,
            character_sheet=lead_sheet,
            primary_table=gm_table,
        )
        StoryProgressFactory(
            story=lead_story,
            character_sheet=lead_sheet,
            current_episode=_episode_for(lead_story),
            is_active=True,
        )
        gm_profiles.append(gm_profile)

        # Stale row (on an episode so it is not also a frontier row).
        stale_sheet = CharacterSheetFactory()
        stale_story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=stale_sheet)
        stale_progress = StoryProgressFactory(
            story=stale_story,
            character_sheet=stale_sheet,
            current_episode=_episode_for(stale_story),
            is_active=True,
        )
        StoryProgressFactory._meta.model.objects.filter(pk=stale_progress.pk).update(
            last_advanced_at=stale_time
        )

        # Waiting-for-GM row (on an episode so it is not also a frontier row).
        waiting_sheet = CharacterSheetFactory()
        waiting_story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=waiting_sheet)
        StoryProgressFactory(
            story=waiting_story,
            character_sheet=waiting_sheet,
            current_episode=_episode_for(waiting_story),
            is_active=True,
            status=ProgressStatus.WAITING_FOR_GM,
        )

        # Frontier row (current_episode=None).
        frontier_sheet = CharacterSheetFactory()
        frontier_story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=frontier_sheet)
        StoryProgressFactory(
            story=frontier_story,
            character_sheet=frontier_sheet,
            current_episode=None,
            is_active=True,
        )
    return gm_profiles


class StaffWorkloadQueryBoundTest(APITestCase):
    """The view must issue a constant number of queries independent of N."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)

    def test_staff_workload_query_count_is_bounded(self):
        # Before the bounding refactor this scan was O(N): N=3 → 29 queries,
        # N=6 → 38 (exactly 3 extra queries per GM). After the refactor the
        # count is a constant independent of N (verified by bumping N here).
        gm_profiles = _build_workload_rows(6)
        self.client.force_authenticate(user=self.staff)
        with self.assertNumQueries(BOUNDED_QUERY_COUNT):
            resp = self.client.get(STAFF_WORKLOAD_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        # Content invariant: dropped-rows regression guard. Every bucket that
        # scales with N must contain exactly our 6 freshly-built rows (other
        # suites run in isolation, so these are the only rows present).
        data = resp.data
        per_gm_ids = {e["gm_profile_id"] for e in data["per_gm_queue_depth"]}
        for gm in gm_profiles:
            assert gm.pk in per_gm_ids
        assert len(data["per_gm_queue_depth"]) == 6
        assert len(data["stale_stories"]) == 6
        assert len(data["stories_waiting_for_gm"]) == 6
        assert len(data["stories_at_frontier"]) == 6
