"""
Tests for vote system models.
"""

import datetime

from django.db import IntegrityError
from django.test import TestCase
from evennia.accounts.models import AccountDB
import pytest

from world.progression.constants import VoteTargetType
from world.progression.models import WeeklyVote, WeeklyVoteBudget


class WeeklyVoteBudgetModelTest(TestCase):
    """Test WeeklyVoteBudget model."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountDB.objects.create(
            username="voter1",
            email="voter1@test.com",
        )
        cls.week_start = datetime.date(2026, 3, 23)  # A Monday

    def setUp(self) -> None:
        WeeklyVoteBudget.flush_instance_cache()

    def test_creation_defaults(self) -> None:
        """Budget created with correct defaults."""
        budget = WeeklyVoteBudget.objects.create(
            account=self.account,
            week_start=self.week_start,
        )
        assert budget.base_votes == 7
        assert budget.scene_bonus_votes == 0
        assert budget.votes_spent == 0

    def test_votes_remaining_base_only(self) -> None:
        """Remaining equals base when no bonus and nothing spent."""
        budget = WeeklyVoteBudget.objects.create(
            account=self.account,
            week_start=self.week_start,
        )
        assert budget.votes_remaining == 7

    def test_votes_remaining_with_bonus(self) -> None:
        """Bonus votes add to remaining."""
        budget = WeeklyVoteBudget.objects.create(
            account=self.account,
            week_start=self.week_start,
            scene_bonus_votes=3,
        )
        assert budget.votes_remaining == 10

    def test_votes_remaining_after_spending(self) -> None:
        """Spending reduces remaining correctly."""
        budget = WeeklyVoteBudget.objects.create(
            account=self.account,
            week_start=self.week_start,
            scene_bonus_votes=2,
            votes_spent=5,
        )
        # 7 base + 2 bonus - 5 spent = 4
        assert budget.votes_remaining == 4

    def test_unique_constraint(self) -> None:
        """Cannot create two budgets for same account + week."""
        WeeklyVoteBudget.objects.create(
            account=self.account,
            week_start=self.week_start,
        )
        with pytest.raises(IntegrityError):
            WeeklyVoteBudget.objects.create(
                account=self.account,
                week_start=self.week_start,
            )

    def test_different_weeks_allowed(self) -> None:
        """Same account can have budgets for different weeks."""
        WeeklyVoteBudget.objects.create(
            account=self.account,
            week_start=self.week_start,
        )
        next_week = self.week_start + datetime.timedelta(weeks=1)
        budget2 = WeeklyVoteBudget.objects.create(
            account=self.account,
            week_start=next_week,
        )
        assert budget2.pk is not None

    def test_str(self) -> None:
        budget = WeeklyVoteBudget.objects.create(
            account=self.account,
            week_start=self.week_start,
            votes_spent=2,
        )
        result = str(budget)
        assert "voter1" in result
        assert "5" in result  # 7 - 2 remaining


class WeeklyVoteModelTest(TestCase):
    """Test WeeklyVote model."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.voter = AccountDB.objects.create(
            username="voter2",
            email="voter2@test.com",
        )
        cls.author = AccountDB.objects.create(
            username="author1",
            email="author1@test.com",
        )
        cls.week_start = datetime.date(2026, 3, 23)

    def setUp(self) -> None:
        WeeklyVote.flush_instance_cache()

    def test_creation(self) -> None:
        """Vote can be created with all required fields."""
        vote = WeeklyVote.objects.create(
            voter=self.voter,
            week_start=self.week_start,
            target_type=VoteTargetType.INTERACTION,
            target_id=42,
            author_account=self.author,
        )
        assert vote.voter == self.voter
        assert vote.target_type == VoteTargetType.INTERACTION
        assert vote.target_id == 42
        assert vote.author_account == self.author
        assert vote.processed is False
        assert vote.created_at is not None

    def test_unique_constraint(self) -> None:
        """Cannot vote on the same target twice in one week."""
        WeeklyVote.objects.create(
            voter=self.voter,
            week_start=self.week_start,
            target_type=VoteTargetType.INTERACTION,
            target_id=42,
            author_account=self.author,
        )
        with pytest.raises(IntegrityError):
            WeeklyVote.objects.create(
                voter=self.voter,
                week_start=self.week_start,
                target_type=VoteTargetType.INTERACTION,
                target_id=42,
                author_account=self.author,
            )

    def test_different_targets_allowed(self) -> None:
        """Same voter can vote on different targets in the same week."""
        WeeklyVote.objects.create(
            voter=self.voter,
            week_start=self.week_start,
            target_type=VoteTargetType.INTERACTION,
            target_id=42,
            author_account=self.author,
        )
        vote2 = WeeklyVote.objects.create(
            voter=self.voter,
            week_start=self.week_start,
            target_type=VoteTargetType.INTERACTION,
            target_id=43,
            author_account=self.author,
        )
        assert vote2.pk is not None

    def test_different_target_types_allowed(self) -> None:
        """Same target_id with different target_type is a distinct vote."""
        WeeklyVote.objects.create(
            voter=self.voter,
            week_start=self.week_start,
            target_type=VoteTargetType.INTERACTION,
            target_id=42,
            author_account=self.author,
        )
        vote2 = WeeklyVote.objects.create(
            voter=self.voter,
            week_start=self.week_start,
            target_type=VoteTargetType.SCENE_PARTICIPATION,
            target_id=42,
            author_account=self.author,
        )
        assert vote2.pk is not None

    def test_str(self) -> None:
        vote = WeeklyVote.objects.create(
            voter=self.voter,
            week_start=self.week_start,
            target_type=VoteTargetType.INTERACTION,
            target_id=42,
            author_account=self.author,
        )
        result = str(vote)
        assert "voter2" in result
        assert "interaction" in result
        assert "42" in result


class VoteTargetTypeTest(TestCase):
    """Test VoteTargetType choices."""

    def test_choices_exist(self) -> None:
        assert VoteTargetType.INTERACTION == "interaction"
        assert VoteTargetType.SCENE_PARTICIPATION == "scene_participation"
        assert VoteTargetType.JOURNAL == "journal"

    def test_max_length_fits(self) -> None:
        """All choice values fit within the max_length=25 constraint."""
        for value, _label in VoteTargetType.choices:
            assert len(value) <= 25, f"{value!r} exceeds 25 chars"
