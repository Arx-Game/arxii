"""
Tests for weekly vote processing service.
"""

from __future__ import annotations

import datetime

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.progression.constants import VoteTargetType
from world.progression.models import WeeklyVote, WeeklyVoteBudget, XPTransaction
from world.progression.services.vote_processing import (
    calculate_vote_xp,
    process_memorable_poses,
    process_weekly_votes,
)
from world.progression.types import ProgressionReason
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import InteractionFactory, PersonaFactory, SceneFactory
from world.scenes.models import Interaction


def _make_character_with_account() -> tuple:
    """Create a character wired up with roster entry, tenure, and account.

    Returns (account, persona) so tests can create interactions and verify XP.
    """
    account = AccountFactory()
    player_data = PlayerDataFactory(account=account)
    persona = PersonaFactory()
    character = persona.character
    entry = RosterEntryFactory(character=character)
    RosterTenureFactory(roster_entry=entry, player_data=player_data)
    return account, persona


class CalculateVoteXPTest(TestCase):
    """Test the diminishing-returns XP curve."""

    def test_zero_votes_yields_zero(self) -> None:
        assert calculate_vote_xp(0) == 0

    def test_negative_votes_yields_zero(self) -> None:
        assert calculate_vote_xp(-5) == 0

    def test_one_vote(self) -> None:
        result = calculate_vote_xp(1)
        assert 3 <= result <= 8, f"Expected ~5 XP for 1 vote, got {result}"

    def test_five_votes(self) -> None:
        result = calculate_vote_xp(5)
        assert 10 <= result <= 16, f"Expected ~12 XP for 5 votes, got {result}"

    def test_ten_votes(self) -> None:
        result = calculate_vote_xp(10)
        assert 14 <= result <= 22, f"Expected ~15-18 XP for 10 votes, got {result}"

    def test_twenty_votes(self) -> None:
        result = calculate_vote_xp(20)
        assert 20 <= result <= 30, f"Expected ~22-25 XP for 20 votes, got {result}"

    def test_fifty_votes(self) -> None:
        result = calculate_vote_xp(50)
        assert 30 <= result <= 50, f"Expected ~35 XP for 50 votes, got {result}"

    def test_hundred_votes_capped_at_fifty(self) -> None:
        result = calculate_vote_xp(100)
        assert result == 50, f"Expected 50 XP cap for 100 votes, got {result}"

    def test_monotonically_increasing(self) -> None:
        """More votes should never yield less XP."""
        prev = 0
        for count in range(150):
            current = calculate_vote_xp(count)
            assert current >= prev, f"XP decreased from {prev} to {current} at {count} votes"
            prev = current


class ProcessWeeklyVotesTest(TestCase):
    """Test the weekly vote processing pipeline."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.week_start = datetime.date(2026, 3, 23)  # A Monday

    def test_awards_xp_based_on_distinct_voters(self) -> None:
        """Each author gets XP based on how many unique voters they received."""
        author_account, author_persona = _make_character_with_account()
        voter1 = AccountFactory()
        voter2 = AccountFactory()

        interaction = InteractionFactory(persona=author_persona)

        for voter in [voter1, voter2]:
            WeeklyVote.objects.create(
                voter=voter,
                week_start=self.week_start,
                target_type=VoteTargetType.INTERACTION,
                target_id=interaction.pk,
                author_account=author_account,
            )

        process_weekly_votes(self.week_start)

        expected_xp = calculate_vote_xp(2)
        txn = XPTransaction.objects.filter(
            account=author_account,
            reason=ProgressionReason.VOTE_REWARD,
        ).first()
        assert txn is not None, "Expected an XP transaction for vote reward"
        assert txn.amount == expected_xp

    def test_marks_votes_as_processed(self) -> None:
        author_account, _ = _make_character_with_account()
        voter = AccountFactory()

        WeeklyVote.objects.create(
            voter=voter,
            week_start=self.week_start,
            target_type=VoteTargetType.INTERACTION,
            target_id=1,
            author_account=author_account,
        )

        process_weekly_votes(self.week_start)

        WeeklyVote.flush_instance_cache()
        assert WeeklyVote.objects.filter(week_start=self.week_start, processed=False).count() == 0
        assert WeeklyVote.objects.filter(week_start=self.week_start, processed=True).count() == 1

    def test_resets_budgets(self) -> None:
        account = AccountFactory()
        WeeklyVoteBudget.objects.create(
            account=account,
            week_start=self.week_start,
            base_votes=7,
            scene_bonus_votes=3,
            votes_spent=5,
        )

        process_weekly_votes(self.week_start)

        WeeklyVoteBudget.flush_instance_cache()
        budget = WeeklyVoteBudget.objects.get(account=account, week_start=self.week_start)
        assert budget.base_votes == 7
        assert budget.scene_bonus_votes == 0
        assert budget.votes_spent == 0

    def test_ignores_already_processed_votes(self) -> None:
        author_account, _ = _make_character_with_account()
        voter = AccountFactory()

        WeeklyVote.objects.create(
            voter=voter,
            week_start=self.week_start,
            target_type=VoteTargetType.INTERACTION,
            target_id=1,
            author_account=author_account,
            processed=True,
        )

        process_weekly_votes(self.week_start)

        assert not XPTransaction.objects.filter(
            account=author_account,
            reason=ProgressionReason.VOTE_REWARD,
        ).exists()

    def test_duplicate_voter_counted_once(self) -> None:
        """Same voter voting on two different targets for the same author counts as 1."""
        author_account, author_persona = _make_character_with_account()
        voter = AccountFactory()

        interaction1 = InteractionFactory(persona=author_persona)
        interaction2 = InteractionFactory(persona=author_persona)

        for interaction in [interaction1, interaction2]:
            WeeklyVote.objects.create(
                voter=voter,
                week_start=self.week_start,
                target_type=VoteTargetType.INTERACTION,
                target_id=interaction.pk,
                author_account=author_account,
            )

        process_weekly_votes(self.week_start)

        expected_xp = calculate_vote_xp(1)
        txn = XPTransaction.objects.get(
            account=author_account,
            reason=ProgressionReason.VOTE_REWARD,
        )
        assert txn.amount == expected_xp


class ProcessMemorablePosesTest(TestCase):
    """Test memorable pose recognition."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.week_start = datetime.date(2026, 3, 23)

    def test_awards_3_2_1_to_top_interactions(self) -> None:
        scene = SceneFactory()
        accounts = []
        for i in range(3):
            account, persona = _make_character_with_account()
            accounts.append(account)
            InteractionFactory(
                persona=persona,
                scene=scene,
                vote_count=10 - i,  # 10, 9, 8
            )

        process_memorable_poses(self.week_start)

        for account, expected_xp in zip(accounts, [3, 2, 1], strict=True):
            txn = XPTransaction.objects.filter(
                account=account,
                reason=ProgressionReason.MEMORABLE_POSE,
            ).first()
            assert txn is not None, f"Expected memorable pose award for account {account.pk}"
            assert txn.amount == expected_xp, (
                f"Expected {expected_xp} XP, got {txn.amount} for account {account.pk}"
            )

    def test_ties_get_higher_tier(self) -> None:
        """Two interactions tied for 1st both get 3 XP."""
        scene = SceneFactory()
        account1, persona1 = _make_character_with_account()
        account2, persona2 = _make_character_with_account()

        InteractionFactory(persona=persona1, scene=scene, vote_count=10)
        InteractionFactory(persona=persona2, scene=scene, vote_count=10)

        process_memorable_poses(self.week_start)

        for account in [account1, account2]:
            txn = XPTransaction.objects.filter(
                account=account,
                reason=ProgressionReason.MEMORABLE_POSE,
            ).first()
            assert txn is not None
            assert txn.amount == 3, f"Tied-for-1st should get 3 XP, got {txn.amount}"

    def test_resets_vote_count_to_zero(self) -> None:
        scene = SceneFactory()
        _, persona = _make_character_with_account()
        interaction = InteractionFactory(persona=persona, scene=scene, vote_count=5)
        voter = AccountFactory()
        WeeklyVote.objects.create(
            voter=voter,
            week_start=self.week_start,
            target_type=VoteTargetType.INTERACTION,
            target_id=interaction.pk,
            author_account=AccountFactory(),
        )

        process_memorable_poses(self.week_start)

        Interaction.flush_instance_cache()
        interaction.refresh_from_db()
        assert interaction.vote_count == 0

    def test_skips_interactions_without_scene(self) -> None:
        """Interactions with no scene should not receive memorable pose awards."""
        account, persona = _make_character_with_account()
        InteractionFactory(persona=persona, scene=None, vote_count=10)

        process_memorable_poses(self.week_start)

        assert not XPTransaction.objects.filter(
            account=account,
            reason=ProgressionReason.MEMORABLE_POSE,
        ).exists()

    def test_resets_sceneless_interaction_vote_count(self) -> None:
        """Sceneless interactions with votes still get their vote_count reset."""
        _, persona = _make_character_with_account()
        interaction = InteractionFactory(persona=persona, scene=None, vote_count=5)
        voter = AccountFactory()
        WeeklyVote.objects.create(
            voter=voter,
            week_start=self.week_start,
            target_type=VoteTargetType.INTERACTION,
            target_id=interaction.pk,
            author_account=AccountFactory(),
        )

        process_memorable_poses(self.week_start)

        Interaction.flush_instance_cache()
        interaction.refresh_from_db()
        assert interaction.vote_count == 0

    def test_multiple_scenes_processed_independently(self) -> None:
        """Each scene gets its own top-3 ranking."""
        scene1 = SceneFactory()
        scene2 = SceneFactory()

        account1, persona1 = _make_character_with_account()
        account2, persona2 = _make_character_with_account()

        InteractionFactory(persona=persona1, scene=scene1, vote_count=10)
        InteractionFactory(persona=persona2, scene=scene2, vote_count=10)

        process_memorable_poses(self.week_start)

        for account in [account1, account2]:
            txn = XPTransaction.objects.filter(
                account=account,
                reason=ProgressionReason.MEMORABLE_POSE,
            ).first()
            assert txn is not None
            assert txn.amount == 3  # Both are 1st in their scene
