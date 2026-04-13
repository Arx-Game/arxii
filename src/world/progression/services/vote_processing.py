"""
Weekly vote processing service.

Runs as a cron task to convert weekly votes into XP awards and
recognize memorable poses (top-voted interactions per scene).
"""

from __future__ import annotations

import logging
from math import log2

from django.db import transaction
from django.db.models import Count
from evennia.accounts.models import AccountDB

from world.game_clock.models import GameWeek
from world.game_clock.week_services import get_current_game_week
from world.progression.constants import MEMORABLE_POSE_XP, VOTE_XP_CAP, VoteTargetType
from world.progression.models import WeeklyVote, WeeklyVoteBudget
from world.progression.services.awards import award_xp
from world.progression.types import ProgressionReason
from world.roster.selectors import get_account_for_character
from world.scenes.models import Interaction

logger = logging.getLogger("world.progression.vote_processing")


def calculate_vote_xp(unique_voter_count: int) -> int:
    """Return XP to award for a given number of unique voters.

    Uses a diminishing-returns curve capped at VOTE_XP_CAP. Zero votes yields 0 XP.
    The formula is intentionally simple and tunable.
    """
    if unique_voter_count <= 0:
        return 0
    raw = 5 * log2(unique_voter_count + 1) + unique_voter_count * 0.3
    return min(VOTE_XP_CAP, int(raw))


def process_memorable_poses(game_week: GameWeek) -> None:
    """Award bonus XP to the top 3 most-voted interactions per scene.

    Ties receive the higher tier (e.g. two tied for 1st both get 3 XP).
    After processing, ALL Interaction.vote_count values are reset to 0.
    """
    logger.info("Processing memorable poses for %s", game_week)
    interactions = (
        Interaction.objects.filter(
            vote_count__gt=0,
            scene__isnull=False,
        )
        .select_related("persona__character_sheet__roster_entry")
        .order_by("scene_id", "-vote_count")
    )

    # Group by scene
    scene_groups: dict[int, list[Interaction]] = {}
    for interaction in interactions:
        scene_id = interaction.scene_id
        if scene_id not in scene_groups:
            scene_groups[scene_id] = []
        scene_groups[scene_id].append(interaction)

    for scene_id, group in scene_groups.items():
        # group is already sorted by -vote_count
        tier_index = 0
        prev_vote_count: int | None = None

        for interaction in group:
            if tier_index >= len(MEMORABLE_POSE_XP):
                break

            # Ties: if same vote_count as previous, same tier
            if prev_vote_count is not None and interaction.vote_count < prev_vote_count:
                tier_index += 1
                if tier_index >= len(MEMORABLE_POSE_XP):
                    break

            xp_amount = MEMORABLE_POSE_XP[tier_index]
            account = get_account_for_character(interaction.persona.character_sheet.character)
            if account is None:
                prev_vote_count = interaction.vote_count
                continue

            try:
                award_xp(
                    account=account,
                    amount=xp_amount,
                    reason=ProgressionReason.MEMORABLE_POSE,
                    description=(
                        f"Memorable pose (#{tier_index + 1}) in scene {scene_id} "
                        f"with {interaction.vote_count} votes"
                    ),
                )
            except Exception:
                logger.exception(
                    "Failed to award memorable pose XP for interaction %d",
                    interaction.pk,
                )

            prev_vote_count = interaction.vote_count

    # Reset vote counts only for interactions that were voted on in the processed week
    voted_interaction_ids = WeeklyVote.objects.filter(
        game_week=game_week,
        target_type=VoteTargetType.INTERACTION,
    ).values_list("target_id", flat=True)
    Interaction.objects.filter(pk__in=voted_interaction_ids, vote_count__gt=0).update(vote_count=0)


def process_weekly_votes(game_week: GameWeek) -> None:
    """Process all unprocessed votes for the given week into XP awards.

    Steps 1-3 (vote XP + mark processed) are atomic so a crash doesn't
    double-award. Memorable poses and budget reset are independent operations
    that run after vote processing completes.
    """
    # Step 1-3: Award vote XP and mark processed (atomic)
    with transaction.atomic():
        unprocessed = WeeklyVote.objects.filter(
            game_week=game_week,
            processed=False,
        )

        author_voter_counts = unprocessed.values("author_account").annotate(
            voter_count=Count("voter", distinct=True),
        )

        for entry in author_voter_counts:
            author_account_id = entry["author_account"]
            voter_count = entry["voter_count"]
            xp_amount = calculate_vote_xp(voter_count)

            if xp_amount <= 0:
                continue

            try:
                account = AccountDB.objects.get(pk=author_account_id)
            except AccountDB.DoesNotExist:
                logger.warning("Author account %d not found, skipping", author_account_id)
                continue

            award_xp(
                account=account,
                amount=xp_amount,
                reason=ProgressionReason.VOTE_REWARD,
                description=f"Weekly vote XP: {voter_count} unique voters",
            )

        unprocessed.update(processed=True)

    # Step 4: Process memorable poses (independent)
    process_memorable_poses(game_week)

    # Step 5: Reset bonus/spent on processed week's budgets (base_votes varies per
    # account based on character count, so we leave it as-is for historical accuracy)
    WeeklyVoteBudget.objects.filter(game_week=game_week).update(
        scene_bonus_votes=0,
        votes_spent=0,
    )


def weekly_vote_processing_task() -> None:
    """Cron task wrapper: process votes for the previous week.

    Looks for the most recent non-current GameWeek (i.e. the one that just ended).
    """
    current = get_current_game_week()
    previous = (
        GameWeek.objects.filter(ended_at__isnull=False)
        .exclude(pk=current.pk)
        .order_by("-started_at")
        .first()
    )
    if previous is None:
        logger.info("No previous game week found; skipping vote processing.")
        return
    logger.info("Starting weekly vote processing for %s", previous)
    process_weekly_votes(previous)
    logger.info("Completed weekly vote processing for %s", previous)
