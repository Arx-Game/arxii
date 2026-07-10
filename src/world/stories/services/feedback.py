"""Story feedback submission — awards GM Story Reward XP for positive GM ratings (#2123).

Rev-2 addendum to the GM Story Reward spec: a served participant's positive
average rating on a story's GM (``StoryFeedback.is_gm_feedback=True``) grants
the reviewed GM ``GM_STORY_REWARD`` XP through the same weekly-capped path as
beat/episode/story-completion awards. Non-positive averages award zero, never
negative — feedback already has trust-score teeth of its own; an XP clawback
would chill honest ratings.

``submit_story_feedback`` is the single convergence point for creating a
``StoryFeedback`` row: it replaces the ORM calls that used to live inline in
``StoryFeedbackCreateSerializer.create`` (Layer 3 of the app's action-endpoint
pattern — service functions do the atomic work, serializers only validate).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db import transaction

from world.gm.models import GMProfile, GMRewardConfig
from world.gm.services import award_gm_story_reward
from world.stories.models import StoryFeedback, StoryParticipation, TrustCategoryFeedbackRating

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.stories.models import Story


@transaction.atomic
def submit_story_feedback(  # noqa: PLR0913
    *,
    story: Story,
    reviewer: AccountDB,
    reviewed_player: AccountDB,
    is_gm_feedback: bool,
    comments: str,
    category_ratings: list[dict[str, Any]],
) -> StoryFeedback:
    """Create a ``StoryFeedback`` row (+ its per-category ratings).

    Uniqueness ``(story, reviewer, reviewed_player)`` is enforced by the model
    — at most one counted feedback per reviewer per (story, reviewed_player)
    pair, satisfying "one counted feedback per player per story" for GM
    feedback (where reviewed_player is fixed as the story's GM). Self-feedback
    is excluded upstream (the input serializer rejects reviewer==reviewed_player
    before this is ever called).

    When ``is_gm_feedback`` is set, also credits the reviewed GM with GM Story
    Reward XP (#2123) — see ``_maybe_award_gm_feedback_xp``.
    """
    feedback = StoryFeedback.objects.create(
        story=story,
        reviewer=reviewer,
        reviewed_player=reviewed_player,
        is_gm_feedback=is_gm_feedback,
        comments=comments,
    )
    for rating_data in category_ratings:
        TrustCategoryFeedbackRating.objects.create(feedback=feedback, **rating_data)

    if is_gm_feedback:
        _maybe_award_gm_feedback_xp(
            feedback=feedback,
            story=story,
            reviewer=reviewer,
            reviewed_player=reviewed_player,
        )

    return feedback


def _maybe_award_gm_feedback_xp(
    *,
    feedback: StoryFeedback,
    story: Story,
    reviewer: AccountDB,
    reviewed_player: AccountDB,
) -> None:
    """Credit the reviewed GM with GM Story Reward XP for a positive rating.

    Guards:
      - The reviewer must be a served participant (a persona seated in this
        story's ``StoryParticipation`` roster) — never a spectator.
      - ``reviewed_player`` must actually be a GM (have a ``GMProfile``).
      - The average rating must be positive; non-positive averages award
        nothing (never negative).

    The XP transaction description is deliberately aggregate ("story
    feedback") — never names the rating player, per the leak rule.
    """
    is_served_participant = StoryParticipation.objects.filter(
        story=story,
        character__db_account=reviewer,
    ).exists()
    if not is_served_participant:
        return

    try:
        gm_profile = reviewed_player.gm_profile
    except GMProfile.DoesNotExist:
        return

    average_rating = feedback.get_average_rating()
    if average_rating <= 0:
        return

    # "5 XP × the 1..N rating band" — the rounded positive average scales the
    # per-rating-point config value. Ratings are bounded -2..2, so this band
    # is always 1 or 2 once average_rating > 0 rounds to a positive int.
    rating_band = round(average_rating)
    if rating_band <= 0:
        return

    config = GMRewardConfig.load()
    per_point = config.feedback_xp_per_rating_point
    award_gm_story_reward(
        gm_profile=gm_profile,
        players_served=rating_band,
        per_player_xp=per_point,
        event_cap=per_point * rating_band,
        description=f"GM reward: story feedback ({rating_band} positive rating point(s))",
    )
