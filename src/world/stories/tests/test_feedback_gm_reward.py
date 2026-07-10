"""Tests for the story-feedback GM Story Reward path (#2123 rev-2 addendum)."""

from django.db import IntegrityError
from django.test import TestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.gm.factories import GMProfileFactory
from world.gm.models import GMRewardConfig
from world.progression.models import XPTransaction
from world.progression.types import ProgressionReason
from world.stories.factories import StoryFactory, StoryParticipationFactory, TrustCategoryFactory
from world.stories.models import StoryFeedback
from world.stories.services.feedback import submit_story_feedback


def _served_participant(story, account):
    """Create a character owned by ``account`` and seat it in ``story``."""
    character = CharacterFactory()
    character.db_account = account
    character.save()
    StoryParticipationFactory(story=story, character=character)
    return character


class SubmitStoryFeedbackGmRewardTests(TestCase):
    def setUp(self) -> None:
        self.story = StoryFactory()
        self.gm = GMProfileFactory()
        self.reviewer = AccountFactory()
        _served_participant(self.story, self.reviewer)

    def test_positive_average_rating_awards_feedback_xp(self) -> None:
        category = TrustCategoryFactory()
        submit_story_feedback(
            story=self.story,
            reviewer=self.reviewer,
            reviewed_player=self.gm.account,
            is_gm_feedback=True,
            comments="Great table, ran a tight session.",
            category_ratings=[{"trust_category": category, "rating": 2}],
        )

        config = GMRewardConfig.load()
        txn = XPTransaction.objects.get(
            account=self.gm.account, reason=ProgressionReason.GM_STORY_REWARD
        )
        # rating=2 ("Excellent") -> rating_band=2 -> feedback_xp_per_rating_point * 2
        self.assertEqual(txn.amount, config.feedback_xp_per_rating_point * 2)

    def test_zero_average_rating_awards_nothing(self) -> None:
        cat1 = TrustCategoryFactory()
        cat2 = TrustCategoryFactory()
        submit_story_feedback(
            story=self.story,
            reviewer=self.reviewer,
            reviewed_player=self.gm.account,
            is_gm_feedback=True,
            comments="Mixed feelings about this session overall.",
            category_ratings=[
                {"trust_category": cat1, "rating": 1},
                {"trust_category": cat2, "rating": -1},
            ],
        )
        self.assertFalse(
            XPTransaction.objects.filter(reason=ProgressionReason.GM_STORY_REWARD).exists()
        )

    def test_negative_average_rating_awards_nothing_never_negative(self) -> None:
        category = TrustCategoryFactory()
        submit_story_feedback(
            story=self.story,
            reviewer=self.reviewer,
            reviewed_player=self.gm.account,
            is_gm_feedback=True,
            comments="Unfortunately this session ran long and unfocused.",
            category_ratings=[{"trust_category": category, "rating": -2}],
        )
        self.assertFalse(
            XPTransaction.objects.filter(reason=ProgressionReason.GM_STORY_REWARD).exists()
        )

    def test_non_gm_feedback_never_awards(self) -> None:
        category = TrustCategoryFactory()
        reviewed_player = AccountFactory()  # not a GM at all
        submit_story_feedback(
            story=self.story,
            reviewer=self.reviewer,
            reviewed_player=reviewed_player,
            is_gm_feedback=False,
            comments="Great scene partner, very engaged.",
            category_ratings=[{"trust_category": category, "rating": 2}],
        )
        self.assertFalse(
            XPTransaction.objects.filter(reason=ProgressionReason.GM_STORY_REWARD).exists()
        )

    def test_spectator_reviewer_awards_nothing(self) -> None:
        """A reviewer with no StoryParticipation in this story is a spectator — excluded."""
        spectator = AccountFactory()
        category = TrustCategoryFactory()
        submit_story_feedback(
            story=self.story,
            reviewer=spectator,
            reviewed_player=self.gm.account,
            is_gm_feedback=True,
            comments="Watched from the sidelines, still had opinions.",
            category_ratings=[{"trust_category": category, "rating": 2}],
        )
        self.assertFalse(
            XPTransaction.objects.filter(reason=ProgressionReason.GM_STORY_REWARD).exists()
        )

    def test_description_does_not_name_the_rating_player(self) -> None:
        category = TrustCategoryFactory()
        submit_story_feedback(
            story=self.story,
            reviewer=self.reviewer,
            reviewed_player=self.gm.account,
            is_gm_feedback=True,
            comments="Great table, ran a tight session.",
            category_ratings=[{"trust_category": category, "rating": 2}],
        )
        txn = XPTransaction.objects.get(
            account=self.gm.account, reason=ProgressionReason.GM_STORY_REWARD
        )
        self.assertNotIn(self.reviewer.username, txn.description)
        self.assertNotIn(self.story.title, txn.description)

    def test_one_counted_feedback_per_player_per_story(self) -> None:
        """StoryFeedback's own uniqueness constraint enforces this — verify it holds."""
        category = TrustCategoryFactory()
        submit_story_feedback(
            story=self.story,
            reviewer=self.reviewer,
            reviewed_player=self.gm.account,
            is_gm_feedback=True,
            comments="First pass feedback for this story.",
            category_ratings=[{"trust_category": category, "rating": 2}],
        )
        with self.assertRaises(IntegrityError):
            submit_story_feedback(
                story=self.story,
                reviewer=self.reviewer,
                reviewed_player=self.gm.account,
                is_gm_feedback=True,
                comments="Trying to submit a second rating for the same story.",
                category_ratings=[{"trust_category": category, "rating": 2}],
            )
        self.assertEqual(
            StoryFeedback.objects.filter(
                story=self.story, reviewer=self.reviewer, reviewed_player=self.gm.account
            ).count(),
            1,
        )
