"""
Tests for vote API views.
"""

from django.test import TestCase
from evennia.accounts.models import AccountDB
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.progression.constants import VoteTargetType
from world.progression.models import WeeklyVote, WeeklyVoteBudget
from world.progression.services.voting import cast_vote, get_current_week_start
from world.scenes.factories import SceneFactory, SceneParticipationFactory


def _flush_caches() -> None:
    """Flush SharedMemoryModel caches for voting models."""
    WeeklyVote.flush_instance_cache()
    WeeklyVoteBudget.flush_instance_cache()


class VoteViewTestCase(TestCase):
    """Base test case with authenticated API client and a scene participation target."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.voter = AccountDB.objects.create_user(
            username="vote_viewer",
            email="vote_viewer@test.com",
            password="testpass123",
        )
        cls.author = AccountFactory()
        cls.scene = SceneFactory()
        cls.participation = SceneParticipationFactory(
            scene=cls.scene,
            account=cls.author,
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.voter)
        _flush_caches()


class CastVoteViewTests(VoteViewTestCase):
    """Tests for POST /api/progression/votes/."""

    def test_cast_vote_returns_201(self) -> None:
        """Casting a vote on a scene participation returns 201."""
        response = self.client.post(
            "/api/progression/votes/",
            {
                "target_type": VoteTargetType.SCENE_PARTICIPATION,
                "target_id": self.participation.pk,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_cast_vote_creates_vote(self) -> None:
        """Casting a vote creates a WeeklyVote record."""
        self.client.post(
            "/api/progression/votes/",
            {
                "target_type": VoteTargetType.SCENE_PARTICIPATION,
                "target_id": self.participation.pk,
            },
            format="json",
        )
        _flush_caches()
        assert WeeklyVote.objects.filter(voter=self.voter).count() == 1

    def test_cast_vote_returns_budget_info(self) -> None:
        """Cast vote response includes budget information."""
        response = self.client.post(
            "/api/progression/votes/",
            {
                "target_type": VoteTargetType.SCENE_PARTICIPATION,
                "target_id": self.participation.pk,
            },
            format="json",
        )
        assert "budget" in response.data
        budget = response.data["budget"]
        assert "base_votes" in budget
        assert "scene_bonus_votes" in budget
        assert "votes_spent" in budget
        assert "votes_remaining" in budget
        assert budget["votes_spent"] == 1
        assert budget["votes_remaining"] == 6

    def test_cast_vote_over_budget_returns_400(self) -> None:
        """Casting when budget is exhausted returns 400."""
        week_start = get_current_week_start()
        WeeklyVoteBudget.objects.create(
            account=self.voter,
            week_start=week_start,
            votes_spent=7,
        )
        _flush_caches()
        response = self.client.post(
            "/api/progression/votes/",
            {
                "target_type": VoteTargetType.SCENE_PARTICIPATION,
                "target_id": self.participation.pk,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_cast_vote_invalid_target_type_returns_400(self) -> None:
        """Invalid target_type returns 400."""
        response = self.client.post(
            "/api/progression/votes/",
            {
                "target_type": "bogus",
                "target_id": 1,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_cast_vote_nonexistent_target_returns_404(self) -> None:
        """Non-existent target_id returns 404."""
        response = self.client.post(
            "/api/progression/votes/",
            {
                "target_type": VoteTargetType.SCENE_PARTICIPATION,
                "target_id": 999999,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_cast_vote_unauthenticated_returns_403(self) -> None:
        """Unauthenticated requests are denied."""
        self.client.force_authenticate(user=None)
        response = self.client.post(
            "/api/progression/votes/",
            {
                "target_type": VoteTargetType.SCENE_PARTICIPATION,
                "target_id": self.participation.pk,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


class UnvoteViewTests(VoteViewTestCase):
    """Tests for DELETE /api/progression/votes/<id>/."""

    def test_unvote_returns_204(self) -> None:
        """Removing a vote returns 204."""
        vote = cast_vote(
            voter_account=self.voter,
            target_type=VoteTargetType.SCENE_PARTICIPATION,
            target_id=self.participation.pk,
            author_account=self.author,
        )
        _flush_caches()
        response = self.client.delete(f"/api/progression/votes/{vote.pk}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_unvote_deletes_vote(self) -> None:
        """Removing a vote deletes the WeeklyVote record."""
        vote = cast_vote(
            voter_account=self.voter,
            target_type=VoteTargetType.SCENE_PARTICIPATION,
            target_id=self.participation.pk,
            author_account=self.author,
        )
        _flush_caches()
        self.client.delete(f"/api/progression/votes/{vote.pk}/")
        _flush_caches()
        assert not WeeklyVote.objects.filter(pk=vote.pk).exists()

    def test_unvote_nonexistent_returns_404(self) -> None:
        """Deleting a non-existent vote returns 404."""
        response = self.client.delete("/api/progression/votes/999999/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_unvote_other_users_vote_returns_404(self) -> None:
        """Cannot delete another user's vote."""
        other_user = AccountDB.objects.create_user(
            username="other_voter",
            email="other@test.com",
            password="testpass123",
        )
        vote = cast_vote(
            voter_account=other_user,
            target_type=VoteTargetType.SCENE_PARTICIPATION,
            target_id=self.participation.pk,
            author_account=self.author,
        )
        _flush_caches()
        response = self.client.delete(f"/api/progression/votes/{vote.pk}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND


class ListVotesViewTests(VoteViewTestCase):
    """Tests for GET /api/progression/votes/."""

    def test_list_votes_returns_current_week(self) -> None:
        """Returns current week's unprocessed votes for the authenticated user."""
        cast_vote(
            voter_account=self.voter,
            target_type=VoteTargetType.SCENE_PARTICIPATION,
            target_id=self.participation.pk,
            author_account=self.author,
        )
        _flush_caches()
        response = self.client.get("/api/progression/votes/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["target_type"] == VoteTargetType.SCENE_PARTICIPATION
        assert response.data[0]["target_id"] == self.participation.pk

    def test_list_votes_excludes_other_users(self) -> None:
        """Does not include votes from other users."""
        other_user = AccountDB.objects.create_user(
            username="other_lister",
            email="other_lister@test.com",
            password="testpass123",
        )
        cast_vote(
            voter_account=other_user,
            target_type=VoteTargetType.SCENE_PARTICIPATION,
            target_id=self.participation.pk,
            author_account=self.author,
        )
        _flush_caches()
        response = self.client.get("/api/progression/votes/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 0

    def test_list_votes_unauthenticated_returns_403(self) -> None:
        """Unauthenticated requests are denied."""
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/progression/votes/")
        assert response.status_code == status.HTTP_403_FORBIDDEN


class VoteBudgetViewTests(VoteViewTestCase):
    """Tests for GET /api/progression/votes/budget/."""

    def test_budget_returns_correct_values(self) -> None:
        """Budget endpoint returns base, bonus, spent, remaining."""
        response = self.client.get("/api/progression/votes/budget/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["base_votes"] == 7
        assert response.data["scene_bonus_votes"] == 0
        assert response.data["votes_spent"] == 0
        assert response.data["votes_remaining"] == 7

    def test_budget_reflects_cast_votes(self) -> None:
        """Budget updates after casting votes."""
        cast_vote(
            voter_account=self.voter,
            target_type=VoteTargetType.SCENE_PARTICIPATION,
            target_id=self.participation.pk,
            author_account=self.author,
        )
        _flush_caches()
        response = self.client.get("/api/progression/votes/budget/")
        assert response.data["votes_spent"] == 1
        assert response.data["votes_remaining"] == 6

    def test_budget_unauthenticated_returns_403(self) -> None:
        """Unauthenticated requests are denied."""
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/progression/votes/budget/")
        assert response.status_code == status.HTTP_403_FORBIDDEN
