"""Tests for AggregateBeatContribution, AssistantGMClaim, and SessionRequest ViewSets.

All three are ReadOnlyModelViewSets — writes go through service-backed action
endpoints (Wave 11). Tests cover the permission matrix and filter parameters.
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core_management.test_utils import suppress_permission_errors
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.stories.constants import (
    AssistantClaimStatus,
    BeatPredicateType,
    SessionRequestStatus,
    StoryScope,
)
from world.stories.factories import (
    AggregateBeatContributionFactory,
    AssistantGMClaimFactory,
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    SessionRequestFactory,
    StoryFactory,
    StoryParticipationFactory,
)

# ---------------------------------------------------------------------------
# AggregateBeatContributionViewSet
# ---------------------------------------------------------------------------


class AggregateBeatContributionViewSetTest(APITestCase):
    """Test AggregateBeatContributionViewSet permission matrix and filters."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)

        # Story owner / Lead GM
        cls.story_owner = AccountFactory()

        # Contributing character's account
        cls.contributor_account = AccountFactory()
        cls.contributor_char = CharacterFactory()
        cls.contributor_char.db_account = cls.contributor_account
        cls.contributor_char.save()
        cls.character_sheet = CharacterSheetFactory(character=cls.contributor_char)

        # Unrelated user
        cls.unrelated = AccountFactory()

        cls.story = StoryFactory(owners=[cls.story_owner])
        cls.chapter = ChapterFactory(story=cls.story)
        cls.episode = EpisodeFactory(chapter=cls.chapter)
        cls.beat = BeatFactory(
            episode=cls.episode,
            predicate_type=BeatPredicateType.AGGREGATE_THRESHOLD,
            required_points=100,
        )
        cls.contribution = AggregateBeatContributionFactory(
            beat=cls.beat,
            character_sheet=cls.character_sheet,
            points=30,
        )

    # ---------- list --------------------------------------------------------

    def test_staff_can_list(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(reverse("aggregatebeatcontribution-list"))
        assert response.status_code == status.HTTP_200_OK

    def test_contributor_can_list_own_contributions(self):
        self.client.force_authenticate(user=self.contributor_account)
        response = self.client.get(reverse("aggregatebeatcontribution-list"))
        assert response.status_code == status.HTTP_200_OK
        ids = [r["id"] for r in response.data["results"]]
        assert self.contribution.id in ids

    def test_story_owner_can_list(self):
        self.client.force_authenticate(user=self.story_owner)
        response = self.client.get(reverse("aggregatebeatcontribution-list"))
        assert response.status_code == status.HTTP_200_OK
        ids = [r["id"] for r in response.data["results"]]
        assert self.contribution.id in ids

    def test_unrelated_user_sees_empty_list(self):
        self.client.force_authenticate(user=self.unrelated)
        response = self.client.get(reverse("aggregatebeatcontribution-list"))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 0

    @suppress_permission_errors
    def test_unauthenticated_cannot_list(self):
        response = self.client.get(reverse("aggregatebeatcontribution-list"))
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    # ---------- write is rejected -------------------------------------------

    @suppress_permission_errors
    def test_post_is_not_allowed(self):
        """POST is not allowed — ReadOnlyModelViewSet."""
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(
            reverse("aggregatebeatcontribution-list"),
            data={"beat": self.beat.id, "points": 10},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    # ---------- filters ------------------------------------------------------

    def test_filter_by_beat(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(
            reverse("aggregatebeatcontribution-list"), {"beat": self.beat.id}
        )
        assert response.status_code == status.HTTP_200_OK
        for r in response.data["results"]:
            assert r["beat"] == self.beat.id

    def test_filter_by_character_sheet(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(
            reverse("aggregatebeatcontribution-list"),
            {"character_sheet": self.character_sheet.pk},
        )
        assert response.status_code == status.HTTP_200_OK
        for r in response.data["results"]:
            assert r["character_sheet"] == self.character_sheet.pk

    def test_filter_by_story(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(
            reverse("aggregatebeatcontribution-list"), {"story": self.story.id}
        )
        assert response.status_code == status.HTTP_200_OK
        ids = [r["id"] for r in response.data["results"]]
        assert self.contribution.id in ids

    # ---------- serializer fields -------------------------------------------

    def test_serializer_fields_present(self):
        self.client.force_authenticate(user=self.staff)
        url = reverse("aggregatebeatcontribution-detail", kwargs={"pk": self.contribution.pk})
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        for field in [
            "id",
            "beat",
            "character_sheet",
            "roster_entry",
            "points",
            "era",
            "source_note",
            "recorded_at",
        ]:
            assert field in response.data, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# AssistantGMClaimViewSet
# ---------------------------------------------------------------------------


class AssistantGMClaimViewSetTest(APITestCase):
    """Test AssistantGMClaimViewSet permission matrix and filters."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)

        # Story owner / Lead GM
        cls.story_owner = AccountFactory()

        # AGM who made the claim
        cls.agm_account = AccountFactory()
        cls.agm_profile = GMProfileFactory(account=cls.agm_account)

        # Another AGM (unrelated)
        cls.other_agm_account = AccountFactory()
        cls.other_agm_profile = GMProfileFactory(account=cls.other_agm_account)

        # Unrelated user
        cls.unrelated = AccountFactory()

        cls.story = StoryFactory(owners=[cls.story_owner])
        cls.chapter = ChapterFactory(story=cls.story)
        cls.episode = EpisodeFactory(chapter=cls.chapter)
        cls.beat = BeatFactory(
            episode=cls.episode,
            agm_eligible=True,
            predicate_type=BeatPredicateType.GM_MARKED,
        )
        cls.claim = AssistantGMClaimFactory(
            beat=cls.beat,
            assistant_gm=cls.agm_profile,
            status=AssistantClaimStatus.REQUESTED,
        )

    # ---------- list --------------------------------------------------------

    def test_staff_can_list(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(reverse("assistantgmclaim-list"))
        assert response.status_code == status.HTTP_200_OK

    def test_claimant_can_list_own_claims(self):
        self.client.force_authenticate(user=self.agm_account)
        response = self.client.get(reverse("assistantgmclaim-list"))
        assert response.status_code == status.HTTP_200_OK
        ids = [r["id"] for r in response.data["results"]]
        assert self.claim.id in ids

    def test_story_owner_can_list(self):
        self.client.force_authenticate(user=self.story_owner)
        response = self.client.get(reverse("assistantgmclaim-list"))
        assert response.status_code == status.HTTP_200_OK
        ids = [r["id"] for r in response.data["results"]]
        assert self.claim.id in ids

    def test_unrelated_user_sees_empty_list(self):
        self.client.force_authenticate(user=self.unrelated)
        response = self.client.get(reverse("assistantgmclaim-list"))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 0

    def test_other_agm_does_not_see_unrelated_claim(self):
        """An AGM who didn't make this claim doesn't see it."""
        self.client.force_authenticate(user=self.other_agm_account)
        response = self.client.get(reverse("assistantgmclaim-list"))
        assert response.status_code == status.HTTP_200_OK
        ids = [r["id"] for r in response.data["results"]]
        assert self.claim.id not in ids

    # ---------- write is rejected -------------------------------------------

    @suppress_permission_errors
    def test_post_is_not_allowed(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(
            reverse("assistantgmclaim-list"),
            data={"beat": self.beat.id},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    # ---------- filters ------------------------------------------------------

    def test_filter_by_beat(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(reverse("assistantgmclaim-list"), {"beat": self.beat.id})
        assert response.status_code == status.HTTP_200_OK
        for r in response.data["results"]:
            assert r["beat"] == self.beat.id

    def test_filter_by_status(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(
            reverse("assistantgmclaim-list"),
            {"status": AssistantClaimStatus.REQUESTED},
        )
        assert response.status_code == status.HTTP_200_OK
        for r in response.data["results"]:
            assert r["status"] == AssistantClaimStatus.REQUESTED

    def test_filter_by_story(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(reverse("assistantgmclaim-list"), {"story": self.story.id})
        assert response.status_code == status.HTTP_200_OK
        ids = [r["id"] for r in response.data["results"]]
        assert self.claim.id in ids

    # ---------- serializer fields -------------------------------------------

    def test_serializer_fields_present(self):
        self.client.force_authenticate(user=self.staff)
        url = reverse("assistantgmclaim-detail", kwargs={"pk": self.claim.pk})
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        for field in [
            "id",
            "beat",
            "assistant_gm",
            "status",
            "approved_by",
            "rejection_note",
            "framing_note",
            "requested_at",
            "updated_at",
        ]:
            assert field in response.data, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# SessionRequestViewSet
# ---------------------------------------------------------------------------


class SessionRequestViewSetTest(APITestCase):
    """Test SessionRequestViewSet permission matrix and filters."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)

        # Story owner
        cls.story_owner = AccountFactory()

        # Participant's account
        cls.participant_account = AccountFactory()
        cls.participant_char = CharacterFactory()
        cls.participant_char.db_account = cls.participant_account
        cls.participant_char.save()

        # Assigned GM
        cls.gm_account = AccountFactory()
        cls.gm_profile = GMProfileFactory(account=cls.gm_account)
        cls.gm_table = GMTableFactory(gm=cls.gm_profile)

        # Unrelated user
        cls.unrelated = AccountFactory()

        cls.story = StoryFactory(scope=StoryScope.GROUP, owners=[cls.story_owner])
        cls.chapter = ChapterFactory(story=cls.story)
        cls.episode = EpisodeFactory(chapter=cls.chapter)
        StoryParticipationFactory(story=cls.story, character=cls.participant_char)
        cls.session_request = SessionRequestFactory(
            episode=cls.episode,
            status=SessionRequestStatus.OPEN,
            assigned_gm=cls.gm_profile,
        )

    # ---------- list --------------------------------------------------------

    def test_staff_can_list(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(reverse("sessionrequest-list"))
        assert response.status_code == status.HTTP_200_OK

    def test_story_owner_can_list(self):
        self.client.force_authenticate(user=self.story_owner)
        response = self.client.get(reverse("sessionrequest-list"))
        assert response.status_code == status.HTTP_200_OK
        ids = [r["id"] for r in response.data["results"]]
        assert self.session_request.id in ids

    def test_participant_can_list(self):
        self.client.force_authenticate(user=self.participant_account)
        response = self.client.get(reverse("sessionrequest-list"))
        assert response.status_code == status.HTTP_200_OK
        ids = [r["id"] for r in response.data["results"]]
        assert self.session_request.id in ids

    def test_assigned_gm_can_list(self):
        self.client.force_authenticate(user=self.gm_account)
        response = self.client.get(reverse("sessionrequest-list"))
        assert response.status_code == status.HTTP_200_OK
        ids = [r["id"] for r in response.data["results"]]
        assert self.session_request.id in ids

    def test_unrelated_user_sees_empty_list(self):
        self.client.force_authenticate(user=self.unrelated)
        response = self.client.get(reverse("sessionrequest-list"))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 0

    @suppress_permission_errors
    def test_unauthenticated_cannot_list(self):
        response = self.client.get(reverse("sessionrequest-list"))
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    # ---------- write is rejected -------------------------------------------

    @suppress_permission_errors
    def test_post_is_not_allowed(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(
            reverse("sessionrequest-list"),
            data={"episode": self.episode.id},
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    # ---------- filters ------------------------------------------------------

    def test_filter_by_episode(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(reverse("sessionrequest-list"), {"episode": self.episode.id})
        assert response.status_code == status.HTTP_200_OK
        ids = [r["id"] for r in response.data["results"]]
        assert self.session_request.id in ids

    def test_filter_by_status(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(
            reverse("sessionrequest-list"), {"status": SessionRequestStatus.OPEN}
        )
        assert response.status_code == status.HTTP_200_OK
        for r in response.data["results"]:
            assert r["status"] == SessionRequestStatus.OPEN

    def test_filter_by_story(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(reverse("sessionrequest-list"), {"story": self.story.id})
        assert response.status_code == status.HTTP_200_OK
        ids = [r["id"] for r in response.data["results"]]
        assert self.session_request.id in ids

    def test_filter_by_assigned_gm(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(
            reverse("sessionrequest-list"), {"assigned_gm": self.gm_profile.id}
        )
        assert response.status_code == status.HTTP_200_OK
        for r in response.data["results"]:
            assert r["assigned_gm"] == self.gm_profile.id

    # ---------- serializer fields -------------------------------------------

    def test_serializer_fields_present(self):
        self.client.force_authenticate(user=self.staff)
        url = reverse("sessionrequest-detail", kwargs={"pk": self.session_request.pk})
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        for field in [
            "id",
            "episode",
            "story_id",
            "status",
            "event",
            "open_to_any_gm",
            "assigned_gm",
            "initiated_by_account",
            "notes",
            "created_at",
            "updated_at",
        ]:
            assert field in response.data, f"Missing field: {field}"

    def test_story_id_computed_correctly(self):
        """story_id field is derived from episode -> chapter -> story."""
        self.client.force_authenticate(user=self.staff)
        url = reverse("sessionrequest-detail", kwargs={"pk": self.session_request.pk})
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["story_id"] == self.story.id
