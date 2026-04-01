"""
Service functions for the weekly voting system.

Players get 7 base votes per week + 1 bonus per scene attended. Votes are
toggleable (cast/uncast) and feed into XP calculations via a weekly cron.
"""

import datetime

from django.db import transaction
from django.db.models import F, QuerySet
from django.db.models.functions import Greatest
from evennia.accounts.models import AccountDB

from world.progression.constants import VoteTargetType
from world.progression.models import WeeklyVote, WeeklyVoteBudget


def get_current_week_start() -> datetime.date:
    """Return the Monday of the current ISO week."""
    today = datetime.datetime.now(tz=datetime.UTC).date()
    return today - datetime.timedelta(days=today.weekday())


def get_or_create_vote_budget(account: AccountDB) -> WeeklyVoteBudget:
    """Return the vote budget for the current week, creating with defaults if needed."""
    week_start = get_current_week_start()
    budget, _ = WeeklyVoteBudget.objects.get_or_create(
        account=account,
        week_start=week_start,
    )
    return budget


MAX_SCENE_BONUS_VOTES = 7


def increment_scene_bonus(account: AccountDB) -> None:
    """Add 1 to scene_bonus_votes for the current week's budget (capped at 7)."""
    budget = get_or_create_vote_budget(account)
    WeeklyVoteBudget.objects.filter(
        pk=budget.pk,
        scene_bonus_votes__lt=MAX_SCENE_BONUS_VOTES,
    ).update(
        scene_bonus_votes=F("scene_bonus_votes") + 1,
    )


@transaction.atomic
def cast_vote(
    voter_account: AccountDB,
    target_type: str,
    target_id: int,
    author_account: AccountDB,
) -> WeeklyVote:
    """
    Cast a vote on a piece of content.

    Atomically creates a WeeklyVote, increments the budget's votes_spent,
    and (for interactions) increments the target's vote_count.

    Args:
        voter_account: The account casting the vote.
        target_type: One of VoteTargetType values.
        target_id: PK of the voted-on object.
        author_account: Account that authored the voted-on content.

    Returns:
        The created WeeklyVote instance.

    Raises:
        ValueError: If budget is exceeded or vote already exists.
    """
    week_start = get_current_week_start()
    budget, _ = WeeklyVoteBudget.objects.select_for_update().get_or_create(
        account=voter_account,
        week_start=week_start,
    )

    if voter_account == author_account:
        msg = "Cannot vote for your own content"
        raise ValueError(msg)

    if budget.votes_remaining <= 0:
        msg = "No votes remaining this week"
        raise ValueError(msg)

    # Check uniqueness before hitting the DB constraint
    already_exists = WeeklyVote.objects.filter(
        voter=voter_account,
        week_start=week_start,
        target_type=target_type,
        target_id=target_id,
    ).exists()
    if already_exists:
        msg = f"Already voted on {target_type}:{target_id} this week"
        raise ValueError(msg)

    vote = WeeklyVote.objects.create(
        voter=voter_account,
        week_start=week_start,
        target_type=target_type,
        target_id=target_id,
        author_account=author_account,
    )

    WeeklyVoteBudget.objects.filter(pk=budget.pk).update(
        votes_spent=F("votes_spent") + 1,
    )

    if target_type == VoteTargetType.INTERACTION:
        from world.scenes.models import Interaction

        Interaction.objects.filter(pk=target_id).update(
            vote_count=F("vote_count") + 1,
        )

    return vote


@transaction.atomic
def remove_vote(
    voter_account: AccountDB,
    target_type: str,
    target_id: int,
) -> None:
    """
    Remove an unprocessed vote for the current week.

    Atomically deletes the WeeklyVote, decrements the budget's votes_spent,
    and (for interactions) decrements the target's vote_count.

    Args:
        voter_account: The account removing the vote.
        target_type: One of VoteTargetType values.
        target_id: PK of the voted-on object.

    Raises:
        ValueError: If vote not found or already processed.
    """
    week_start = get_current_week_start()

    try:
        vote = WeeklyVote.objects.select_for_update().get(
            voter=voter_account,
            week_start=week_start,
            target_type=target_type,
            target_id=target_id,
        )
    except WeeklyVote.DoesNotExist:
        msg = f"No vote found for {target_type}:{target_id} this week"
        raise ValueError(msg) from None

    if vote.processed:
        msg = "Cannot remove a processed vote"
        raise ValueError(msg)

    vote.delete()

    WeeklyVoteBudget.objects.filter(
        account=voter_account,
        week_start=week_start,
    ).update(votes_spent=Greatest(F("votes_spent") - 1, 0))

    if target_type == VoteTargetType.INTERACTION:
        from world.scenes.models import Interaction

        Interaction.objects.filter(pk=target_id).update(
            vote_count=Greatest(F("vote_count") - 1, 0),
        )


def get_vote_state(
    voter_account: AccountDB,
    target_type: str,
    target_id: int,
) -> bool:
    """Return whether the voter has an unprocessed vote for this target this week."""
    week_start = get_current_week_start()
    return WeeklyVote.objects.filter(
        voter=voter_account,
        week_start=week_start,
        target_type=target_type,
        target_id=target_id,
        processed=False,
    ).exists()


def get_votes_by_voter(voter_account: AccountDB) -> QuerySet[WeeklyVote]:
    """Return all unprocessed votes for the current week."""
    week_start = get_current_week_start()
    return WeeklyVote.objects.filter(
        voter=voter_account,
        week_start=week_start,
        processed=False,
    )
