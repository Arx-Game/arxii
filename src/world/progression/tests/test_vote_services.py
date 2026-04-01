"""
Tests for vote service functions.
"""

import datetime
from unittest.mock import patch

from django.test import TestCase
from evennia.accounts.models import AccountDB

from world.progression.constants import VoteTargetType
from world.progression.models import WeeklyVote, WeeklyVoteBudget
from world.progression.services.voting import (
    cast_vote,
    get_current_week_start,
    get_or_create_vote_budget,
    get_vote_state,
    get_votes_by_voter,
    increment_scene_bonus,
    remove_vote,
)
from world.scenes.factories import InteractionFactory, SceneFactory
from world.scenes.models import Interaction


def _fresh_budget(account: AccountDB) -> WeeklyVoteBudget:
    """Flush cache and return a fresh budget from the DB."""
    WeeklyVoteBudget.flush_instance_cache()
    return WeeklyVoteBudget.objects.get(account=account)


class GetCurrentWeekStartTest(TestCase):
    """Test get_current_week_start utility."""

    def test_returns_a_monday(self) -> None:
        """Week start is always a Monday (weekday 0)."""
        result = get_current_week_start()
        assert result.weekday() == 0

    def test_returns_monday_on_a_wednesday(self) -> None:
        """When today is Wednesday, returns the preceding Monday."""
        wednesday = datetime.datetime(2026, 3, 25, tzinfo=datetime.UTC)
        with patch("world.progression.services.voting.datetime.datetime") as mock_dt:
            mock_dt.now.return_value = wednesday
            result = get_current_week_start()
        assert result == datetime.date(2026, 3, 23)

    def test_returns_same_day_on_monday(self) -> None:
        """When today is Monday, returns today."""
        monday = datetime.datetime(2026, 3, 23, tzinfo=datetime.UTC)
        with patch("world.progression.services.voting.datetime.datetime") as mock_dt:
            mock_dt.now.return_value = monday
            result = get_current_week_start()
        assert result == datetime.date(2026, 3, 23)


class GetOrCreateVoteBudgetTest(TestCase):
    """Test get_or_create_vote_budget."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountDB.objects.create(
            username="budget_test",
            email="budget@test.com",
        )

    def setUp(self) -> None:
        WeeklyVoteBudget.flush_instance_cache()

    def test_creates_budget_with_defaults(self) -> None:
        """First call creates a budget with default values."""
        budget = get_or_create_vote_budget(self.account)
        assert budget.pk is not None
        assert budget.base_votes == 7
        assert budget.scene_bonus_votes == 0
        assert budget.votes_spent == 0

    def test_returns_existing_budget(self) -> None:
        """Second call returns the same budget object."""
        budget1 = get_or_create_vote_budget(self.account)
        budget2 = get_or_create_vote_budget(self.account)
        assert budget1.pk == budget2.pk


class IncrementSceneBonusTest(TestCase):
    """Test increment_scene_bonus."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountDB.objects.create(
            username="bonus_test",
            email="bonus@test.com",
        )

    def setUp(self) -> None:
        WeeklyVoteBudget.flush_instance_cache()

    def test_increments_bonus_votes(self) -> None:
        """Scene bonus increments by 1."""
        get_or_create_vote_budget(self.account)
        increment_scene_bonus(self.account)
        budget = _fresh_budget(self.account)
        assert budget.scene_bonus_votes == 1

    def test_increments_multiple_times(self) -> None:
        """Multiple calls increment cumulatively."""
        get_or_create_vote_budget(self.account)
        increment_scene_bonus(self.account)
        increment_scene_bonus(self.account)
        increment_scene_bonus(self.account)
        budget = _fresh_budget(self.account)
        assert budget.scene_bonus_votes == 3

    def test_creates_budget_if_needed(self) -> None:
        """Budget is auto-created if it doesn't exist yet."""
        increment_scene_bonus(self.account)
        budget = _fresh_budget(self.account)
        assert budget.scene_bonus_votes == 1


class CastVoteTest(TestCase):
    """Test cast_vote service function."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.voter = AccountDB.objects.create(
            username="cast_voter",
            email="cast_voter@test.com",
        )
        cls.author = AccountDB.objects.create(
            username="cast_author",
            email="cast_author@test.com",
        )
        cls.scene = SceneFactory()
        cls.interaction = InteractionFactory(scene=cls.scene)

    def setUp(self) -> None:
        WeeklyVoteBudget.flush_instance_cache()
        WeeklyVote.flush_instance_cache()
        Interaction.flush_instance_cache()

    def test_cast_vote_success(self) -> None:
        """Casting a vote creates a WeeklyVote and increments votes_spent."""
        vote = cast_vote(
            voter_account=self.voter,
            target_type=VoteTargetType.INTERACTION,
            target_id=self.interaction.pk,
            author_account=self.author,
        )
        assert vote.pk is not None
        assert vote.voter == self.voter
        assert vote.target_type == VoteTargetType.INTERACTION
        assert vote.target_id == self.interaction.pk

        budget = _fresh_budget(self.voter)
        assert budget.votes_spent == 1

    def test_cast_vote_increments_interaction_vote_count(self) -> None:
        """Casting on an interaction increments Interaction.vote_count."""
        cast_vote(
            voter_account=self.voter,
            target_type=VoteTargetType.INTERACTION,
            target_id=self.interaction.pk,
            author_account=self.author,
        )
        Interaction.flush_instance_cache()
        self.interaction.refresh_from_db()
        assert self.interaction.vote_count == 1

    def test_cast_vote_no_increment_for_non_interaction(self) -> None:
        """Non-interaction target types do not touch Interaction.vote_count."""
        cast_vote(
            voter_account=self.voter,
            target_type=VoteTargetType.JOURNAL,
            target_id=999,
            author_account=self.author,
        )
        Interaction.flush_instance_cache()
        self.interaction.refresh_from_db()
        assert self.interaction.vote_count == 0

    def test_cast_vote_over_budget_raises(self) -> None:
        """Raises ValueError when no votes remain."""
        week_start = get_current_week_start()
        WeeklyVoteBudget.objects.create(
            account=self.voter,
            week_start=week_start,
            votes_spent=7,  # All base votes used
        )
        with self.assertRaises(ValueError, msg="No votes remaining"):
            cast_vote(
                voter_account=self.voter,
                target_type=VoteTargetType.INTERACTION,
                target_id=self.interaction.pk,
                author_account=self.author,
            )

    def test_cast_vote_duplicate_raises(self) -> None:
        """Raises ValueError when voting on the same target twice."""
        cast_vote(
            voter_account=self.voter,
            target_type=VoteTargetType.INTERACTION,
            target_id=self.interaction.pk,
            author_account=self.author,
        )
        with self.assertRaises(ValueError, msg="Already voted"):
            cast_vote(
                voter_account=self.voter,
                target_type=VoteTargetType.INTERACTION,
                target_id=self.interaction.pk,
                author_account=self.author,
            )


class RemoveVoteTest(TestCase):
    """Test remove_vote service function."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.voter = AccountDB.objects.create(
            username="rm_voter",
            email="rm_voter@test.com",
        )
        cls.author = AccountDB.objects.create(
            username="rm_author",
            email="rm_author@test.com",
        )
        cls.scene = SceneFactory()
        cls.interaction = InteractionFactory(scene=cls.scene)

    def setUp(self) -> None:
        WeeklyVoteBudget.flush_instance_cache()
        WeeklyVote.flush_instance_cache()
        Interaction.flush_instance_cache()

    def test_remove_vote_success(self) -> None:
        """Removing a vote deletes it and decrements votes_spent."""
        cast_vote(
            voter_account=self.voter,
            target_type=VoteTargetType.INTERACTION,
            target_id=self.interaction.pk,
            author_account=self.author,
        )
        WeeklyVote.flush_instance_cache()
        remove_vote(
            voter_account=self.voter,
            target_type=VoteTargetType.INTERACTION,
            target_id=self.interaction.pk,
        )
        budget = _fresh_budget(self.voter)
        assert budget.votes_spent == 0
        assert not WeeklyVote.objects.filter(voter=self.voter).exists()

    def test_remove_vote_decrements_interaction_vote_count(self) -> None:
        """Removing an interaction vote decrements Interaction.vote_count."""
        cast_vote(
            voter_account=self.voter,
            target_type=VoteTargetType.INTERACTION,
            target_id=self.interaction.pk,
            author_account=self.author,
        )
        Interaction.flush_instance_cache()
        self.interaction.refresh_from_db()
        assert self.interaction.vote_count == 1

        WeeklyVote.flush_instance_cache()
        remove_vote(
            voter_account=self.voter,
            target_type=VoteTargetType.INTERACTION,
            target_id=self.interaction.pk,
        )
        Interaction.flush_instance_cache()
        self.interaction.refresh_from_db()
        assert self.interaction.vote_count == 0

    def test_remove_processed_vote_raises(self) -> None:
        """Raises ValueError when trying to remove a processed vote."""
        vote = cast_vote(
            voter_account=self.voter,
            target_type=VoteTargetType.INTERACTION,
            target_id=self.interaction.pk,
            author_account=self.author,
        )
        WeeklyVote.objects.filter(pk=vote.pk).update(processed=True)
        WeeklyVote.flush_instance_cache()
        with self.assertRaises(ValueError, msg="Cannot remove a processed vote"):
            remove_vote(
                voter_account=self.voter,
                target_type=VoteTargetType.INTERACTION,
                target_id=self.interaction.pk,
            )

    def test_remove_nonexistent_vote_raises(self) -> None:
        """Raises ValueError when no matching vote exists."""
        with self.assertRaises(ValueError, msg="No vote found"):
            remove_vote(
                voter_account=self.voter,
                target_type=VoteTargetType.INTERACTION,
                target_id=99999,
            )


class GetVoteStateTest(TestCase):
    """Test get_vote_state."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.voter = AccountDB.objects.create(
            username="state_voter",
            email="state_voter@test.com",
        )
        cls.author = AccountDB.objects.create(
            username="state_author",
            email="state_author@test.com",
        )

    def setUp(self) -> None:
        WeeklyVoteBudget.flush_instance_cache()
        WeeklyVote.flush_instance_cache()

    def test_returns_true_when_voted(self) -> None:
        """Returns True when an unprocessed vote exists."""
        cast_vote(
            voter_account=self.voter,
            target_type=VoteTargetType.JOURNAL,
            target_id=10,
            author_account=self.author,
        )
        assert get_vote_state(self.voter, VoteTargetType.JOURNAL, 10) is True

    def test_returns_false_when_not_voted(self) -> None:
        """Returns False when no vote exists."""
        assert get_vote_state(self.voter, VoteTargetType.JOURNAL, 10) is False

    def test_returns_false_for_processed_vote(self) -> None:
        """Returns False when the vote is processed."""
        vote = cast_vote(
            voter_account=self.voter,
            target_type=VoteTargetType.JOURNAL,
            target_id=20,
            author_account=self.author,
        )
        WeeklyVote.objects.filter(pk=vote.pk).update(processed=True)
        assert get_vote_state(self.voter, VoteTargetType.JOURNAL, 20) is False


class GetVotesByVoterTest(TestCase):
    """Test get_votes_by_voter."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.voter = AccountDB.objects.create(
            username="list_voter",
            email="list_voter@test.com",
        )
        cls.author = AccountDB.objects.create(
            username="list_author",
            email="list_author@test.com",
        )

    def setUp(self) -> None:
        WeeklyVoteBudget.flush_instance_cache()
        WeeklyVote.flush_instance_cache()

    def test_returns_current_week_votes(self) -> None:
        """Returns all unprocessed votes for the current week."""
        cast_vote(self.voter, VoteTargetType.JOURNAL, 1, self.author)
        cast_vote(self.voter, VoteTargetType.JOURNAL, 2, self.author)
        votes = get_votes_by_voter(self.voter)
        assert votes.count() == 2

    def test_excludes_processed_votes(self) -> None:
        """Processed votes are excluded from the result."""
        vote = cast_vote(self.voter, VoteTargetType.JOURNAL, 3, self.author)
        WeeklyVote.objects.filter(pk=vote.pk).update(processed=True)
        votes = get_votes_by_voter(self.voter)
        assert votes.count() == 0

    def test_excludes_other_weeks(self) -> None:
        """Votes from other weeks are excluded."""
        cast_vote(self.voter, VoteTargetType.JOURNAL, 4, self.author)
        # Manually create a vote for last week
        last_week = get_current_week_start() - datetime.timedelta(weeks=1)
        WeeklyVote.objects.create(
            voter=self.voter,
            week_start=last_week,
            target_type=VoteTargetType.JOURNAL,
            target_id=5,
            author_account=self.author,
        )
        votes = get_votes_by_voter(self.voter)
        assert votes.count() == 1
