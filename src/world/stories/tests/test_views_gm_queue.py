"""Tests for GMQueueView — GET /api/stories/gm-queue/.

Scenarios:
- Unauthenticated → 401/403.
- Authenticated user without GMProfile → 403.
- Lead GM with no stories → empty lists.
- Lead GM with an episode-ready story → entry in episodes_ready_to_run.
- Pending AGM claims on Lead GM's stories → entry in pending_agm_claims.
- SessionRequests assigned to the GM → entry in assigned_session_requests.
- Response shape has all required top-level keys.
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core_management.test_utils import suppress_permission_errors
from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.stories.constants import (
    AssistantClaimStatus,
    BeatPredicateType,
    SessionRequestStatus,
    StoryScope,
    TransitionMode,
)
from world.stories.factories import (
    AssistantGMClaimFactory,
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    SessionRequestFactory,
    StoryFactory,
    StoryProgressFactory,
    TransitionFactory,
)

GM_QUEUE_URL = reverse("stories-gm-queue")


def _make_lead_gm():
    """Return (account, gm_profile, gm_table) for a fresh Lead GM."""
    account = AccountFactory()
    profile = GMProfileFactory(account=account)
    table = GMTableFactory(gm=profile)
    return account, profile, table


class GMQueueAuthTest(APITestCase):
    """Authentication and GMProfile permission gate."""

    @suppress_permission_errors
    def test_unauthenticated_rejected(self):
        response = self.client.get(GM_QUEUE_URL)
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    @suppress_permission_errors
    def test_authenticated_without_gm_profile_rejected(self):
        user = AccountFactory()
        self.client.force_authenticate(user=user)
        response = self.client.get(GM_QUEUE_URL)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_lead_gm_gets_200(self):
        account, _profile, _table = _make_lead_gm()
        self.client.force_authenticate(user=account)
        response = self.client.get(GM_QUEUE_URL)
        assert response.status_code == status.HTTP_200_OK


class GMQueueResponseShapeTest(APITestCase):
    """Response contains the expected top-level keys."""

    @classmethod
    def setUpTestData(cls):
        cls.account, cls.profile, cls.table = _make_lead_gm()

    def test_response_has_all_keys(self):
        self.client.force_authenticate(user=self.account)
        response = self.client.get(GM_QUEUE_URL)
        assert response.status_code == status.HTTP_200_OK
        assert "episodes_ready_to_run" in response.data
        assert "pending_agm_claims" in response.data
        assert "assigned_session_requests" in response.data

    def test_empty_gm_gets_empty_lists(self):
        self.client.force_authenticate(user=self.account)
        response = self.client.get(GM_QUEUE_URL)
        assert response.data["episodes_ready_to_run"] == []
        assert response.data["pending_agm_claims"] == []
        assert response.data["assigned_session_requests"] == []


class GMQueueEpisodesReadyTest(APITestCase):
    """Episodes ready to run appear when eligible transitions exist."""

    @classmethod
    def setUpTestData(cls):
        cls.account, cls.profile, cls.table = _make_lead_gm()

        # CHARACTER-scope story whose primary table is our GM's table.
        cls.char_sheet = CharacterSheetFactory()
        cls.story = StoryFactory(
            scope=StoryScope.CHARACTER,
            character_sheet=cls.char_sheet,
            primary_table=cls.table,
        )
        cls.chapter = ChapterFactory(story=cls.story, order=1)
        cls.episode = EpisodeFactory(chapter=cls.chapter, order=1)
        cls.next_ep = EpisodeFactory(chapter=cls.chapter, order=2)
        # Eligible transition: AUTO with no routing requirements.
        cls.transition = TransitionFactory(
            source_episode=cls.episode,
            target_episode=cls.next_ep,
            mode=TransitionMode.AUTO,
        )
        cls.progress = StoryProgressFactory(
            story=cls.story,
            character_sheet=cls.char_sheet,
            current_episode=cls.episode,
        )

    def test_ready_episode_in_episodes_ready_to_run(self):
        self.client.force_authenticate(user=self.account)
        response = self.client.get(GM_QUEUE_URL)
        assert response.status_code == status.HTTP_200_OK
        ready = response.data["episodes_ready_to_run"]
        episode_ids = [e["episode_id"] for e in ready]
        assert self.episode.pk in episode_ids

    def test_ready_entry_shape(self):
        self.client.force_authenticate(user=self.account)
        response = self.client.get(GM_QUEUE_URL)
        ready = response.data["episodes_ready_to_run"]
        matching = [e for e in ready if e["episode_id"] == self.episode.pk]
        assert len(matching) == 1
        entry = matching[0]
        for field in [
            "story_id",
            "story_title",
            "scope",
            "episode_id",
            "episode_title",
            "progress_type",
            "progress_id",
            "eligible_transitions",
            "open_session_request_id",
        ]:
            assert field in entry, f"Missing field: {field}"

    def test_eligible_transitions_serialized(self):
        self.client.force_authenticate(user=self.account)
        response = self.client.get(GM_QUEUE_URL)
        ready = response.data["episodes_ready_to_run"]
        matching = [e for e in ready if e["episode_id"] == self.episode.pk]
        transitions = matching[0]["eligible_transitions"]
        assert len(transitions) >= 1
        assert "transition_id" in transitions[0]
        assert "mode" in transitions[0]


class GMQueuePendingClaimsTest(APITestCase):
    """Pending AGM claims on Lead GM's stories appear in the queue."""

    @classmethod
    def setUpTestData(cls):
        cls.account, cls.profile, cls.table = _make_lead_gm()

        cls.char_sheet = CharacterSheetFactory()
        cls.story = StoryFactory(
            scope=StoryScope.CHARACTER,
            character_sheet=cls.char_sheet,
            primary_table=cls.table,
        )
        cls.chapter = ChapterFactory(story=cls.story, order=1)
        cls.episode = EpisodeFactory(chapter=cls.chapter, order=1)
        cls.beat = BeatFactory(
            episode=cls.episode,
            agm_eligible=True,
            predicate_type=BeatPredicateType.GM_MARKED,
        )
        # AGM claim in REQUESTED state.
        cls.agm_profile = GMProfileFactory()
        cls.claim = AssistantGMClaimFactory(
            beat=cls.beat,
            assistant_gm=cls.agm_profile,
            status=AssistantClaimStatus.REQUESTED,
        )

    def test_pending_claim_appears(self):
        self.client.force_authenticate(user=self.account)
        response = self.client.get(GM_QUEUE_URL)
        assert response.status_code == status.HTTP_200_OK
        claims = response.data["pending_agm_claims"]
        claim_ids = [c["claim_id"] for c in claims]
        assert self.claim.pk in claim_ids

    def test_pending_claim_shape(self):
        self.client.force_authenticate(user=self.account)
        response = self.client.get(GM_QUEUE_URL)
        claims = response.data["pending_agm_claims"]
        matching = [c for c in claims if c["claim_id"] == self.claim.pk]
        assert len(matching) == 1
        entry = matching[0]
        for field in [
            "claim_id",
            "beat_id",
            "beat_internal_description",
            "story_title",
            "assistant_gm_id",
            "requested_at",
        ]:
            assert field in entry, f"Missing field: {field}"


class GMQueueAssignedSessionRequestsTest(APITestCase):
    """SessionRequests assigned to the GM appear in assigned_session_requests."""

    @classmethod
    def setUpTestData(cls):
        cls.account, cls.profile, cls.table = _make_lead_gm()

        cls.char_sheet = CharacterSheetFactory()
        cls.story = StoryFactory(
            scope=StoryScope.CHARACTER,
            character_sheet=cls.char_sheet,
            primary_table=cls.table,
        )
        cls.chapter = ChapterFactory(story=cls.story, order=1)
        cls.episode = EpisodeFactory(chapter=cls.chapter, order=1)
        cls.session_req = SessionRequestFactory(
            episode=cls.episode,
            assigned_gm=cls.profile,
            status=SessionRequestStatus.OPEN,
        )

    def test_assigned_request_appears(self):
        self.client.force_authenticate(user=self.account)
        response = self.client.get(GM_QUEUE_URL)
        assert response.status_code == status.HTTP_200_OK
        assigned = response.data["assigned_session_requests"]
        req_ids = [r["session_request_id"] for r in assigned]
        assert self.session_req.pk in req_ids

    def test_assigned_request_shape(self):
        self.client.force_authenticate(user=self.account)
        response = self.client.get(GM_QUEUE_URL)
        assigned = response.data["assigned_session_requests"]
        matching = [r for r in assigned if r["session_request_id"] == self.session_req.pk]
        assert len(matching) == 1
        entry = matching[0]
        for field in [
            "session_request_id",
            "episode_id",
            "episode_title",
            "story_title",
            "status",
            "event_id",
        ]:
            assert field in entry, f"Missing field: {field}"

    def test_other_gms_requests_not_included(self):
        """Sessions assigned to a different GM should not appear."""
        other_profile = GMProfileFactory()
        other_req = SessionRequestFactory(
            episode=self.episode,
            assigned_gm=other_profile,
            status=SessionRequestStatus.OPEN,
        )
        self.client.force_authenticate(user=self.account)
        response = self.client.get(GM_QUEUE_URL)
        assigned = response.data["assigned_session_requests"]
        req_ids = [r["session_request_id"] for r in assigned]
        assert other_req.pk not in req_ids
        other_req.delete()
