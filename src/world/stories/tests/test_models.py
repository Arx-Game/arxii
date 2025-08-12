from django.test import TestCase

from evennia_extensions.factories import (
    AccountFactory,
    CharacterFactory,
    GMCharacterFactory,
)
from world.stories.factories import (
    ChapterFactory,
    EpisodeFactory,
    PersonalStoryFactory,
    PlayerTrustFactory,
    StoryFactory,
    StoryParticipationFactory,
)
from world.stories.models import (
    Chapter,
    Episode,
    PlayerTrustLevel,
    StoryTrustRequirement,
    TrustCategory,
)
from world.stories.types import (
    ParticipationLevel,
    StoryPrivacy,
    StoryStatus,
    TrustLevel,
)


class StoryModelTestCase(TestCase):
    """Test Story model methods and properties"""

    @classmethod
    def setUpTestData(cls):
        """Create test data once for the entire test class"""
        cls.user = AccountFactory()
        cls.story = StoryFactory()
        cls.private_story = StoryFactory(privacy=StoryPrivacy.PRIVATE)
        # Create a character for the personal story
        personal_char = CharacterFactory()
        cls.personal_story = PersonalStoryFactory(
            personal_story_character=personal_char
        )

    def test_story_trust_requirements_affect_player_application(self):
        """Test that trust requirements prevent/allow player applications"""

        # Get or create trust categories (migration may have created them)
        antagonism_cat, _ = TrustCategory.objects.get_or_create(
            name="test_antagonism",
            defaults={"display_name": "Test Antagonism", "description": "Test"},
        )
        political_cat, _ = TrustCategory.objects.get_or_create(
            name="test_political",
            defaults={"display_name": "Test Political", "description": "Test"},
        )

        # Add trust requirements to story
        StoryTrustRequirement.objects.create(
            story=self.story,
            trust_category=antagonism_cat,
            minimum_trust_level=TrustLevel.BASIC,
        )
        StoryTrustRequirement.objects.create(
            story=self.story,
            trust_category=political_cat,
            minimum_trust_level=TrustLevel.INTERMEDIATE,
        )

        # Create a trust profile for the user
        from world.stories.models import PlayerTrust

        trust_profile, _ = PlayerTrust.objects.get_or_create(account=self.user)

        # User with no trust levels should not be able to apply
        self.assertFalse(self.story.can_player_apply(self.user))

        # Give user basic antagonism trust but not political
        PlayerTrustLevel.objects.create(
            player_trust=trust_profile,
            trust_category=antagonism_cat,
            trust_level=TrustLevel.BASIC,
        )
        self.assertFalse(
            self.story.can_player_apply(self.user)
        )  # Still missing political

        # Give user intermediate political trust - now they should be able to apply
        PlayerTrustLevel.objects.create(
            player_trust=trust_profile,
            trust_category=political_cat,
            trust_level=TrustLevel.INTERMEDIATE,
        )
        self.assertTrue(self.story.can_player_apply(self.user))

    def test_is_active_returns_false_without_gms(self):
        """Test that stories without active GMs are not considered active"""
        self.story.status = StoryStatus.ACTIVE
        self.story.save()
        self.assertFalse(self.story.is_active())

    def test_is_active_returns_true_with_gms(self):
        """Test that stories with active GMs and active status are active"""

        gm_char = GMCharacterFactory()

        self.story.status = StoryStatus.ACTIVE
        self.story.active_gms.add(gm_char)
        self.story.save()

        self.assertTrue(self.story.is_active())

    def test_can_player_apply_to_public_story(self):
        """Test that players can apply to public stories"""
        self.assertTrue(self.story.can_player_apply(self.user))

    def test_cannot_player_apply_to_private_story(self):
        """Test that players cannot apply to private stories by default"""
        self.assertFalse(self.private_story.can_player_apply(self.user))

    def test_personal_story_has_character(self):
        """Test that personal stories have an associated character"""
        self.assertTrue(self.personal_story.is_personal_story)
        self.assertIsNotNone(self.personal_story.personal_story_character)


class StoryParticipationModelTestCase(TestCase):
    """Test StoryParticipation model methods"""

    @classmethod
    def setUpTestData(cls):
        """Create test data once for the entire test class"""
        cls.story = StoryFactory()
        cls.character = CharacterFactory()
        cls.participation = StoryParticipationFactory(
            story=cls.story, character=cls.character
        )

    def test_participation_defaults(self):
        """Test that participation has correct default values"""
        self.assertEqual(
            self.participation.participation_level, ParticipationLevel.OPTIONAL
        )
        self.assertFalse(self.participation.trusted_by_owner)
        self.assertTrue(self.participation.is_active)


class ChapterModelTestCase(TestCase):
    """Test Chapter model methods"""

    @classmethod
    def setUpTestData(cls):
        """Create test data once for the entire test class"""
        cls.story = StoryFactory()
        cls.chapter = ChapterFactory(story=cls.story, order=1)

    def test_chapter_ordering(self):
        """Test that chapters are ordered by story and order"""
        chapter2 = ChapterFactory(story=self.story, order=2)
        chapters = Chapter.objects.filter(story=self.story)

        self.assertEqual(list(chapters), [self.chapter, chapter2])


class EpisodeModelTestCase(TestCase):
    """Test Episode model methods"""

    @classmethod
    def setUpTestData(cls):
        """Create test data once for the entire test class"""
        cls.story = StoryFactory()
        cls.chapter = ChapterFactory(story=cls.story)
        cls.episode = EpisodeFactory(chapter=cls.chapter, order=1)

    def test_episode_ordering(self):
        """Test that episodes are ordered by chapter and order"""
        episode2 = EpisodeFactory(chapter=self.chapter, order=2)
        episodes = Episode.objects.filter(chapter=self.chapter)

        self.assertEqual(list(episodes), [self.episode, episode2])


class PlayerTrustModelTestCase(TestCase):
    """Test PlayerTrust model methods"""

    @classmethod
    def setUpTestData(cls):
        """Create test data once for the entire test class"""
        cls.user = AccountFactory()
        cls.trust_profile = PlayerTrustFactory(account=cls.user)

    def test_get_trust_level_for_category(self):
        """Test getting trust level for specific trust categories"""

        # Create a trust category
        category, _ = TrustCategory.objects.get_or_create(
            name="test_category_specific",
            defaults={
                "display_name": "Test Category",
                "description": "A test category",
            },
        )

        # Create a trust level for this user and category
        PlayerTrustLevel.objects.create(
            player_trust=self.trust_profile,
            trust_category=category,
            trust_level=TrustLevel.INTERMEDIATE,
        )

        trust_level = self.trust_profile.get_trust_level_for_category(category)
        self.assertEqual(trust_level, TrustLevel.INTERMEDIATE)

    def test_get_trust_level_for_nonexistent_category(self):
        """Test getting trust level for category with no PlayerTrustLevel returns untrusted"""

        category, _ = TrustCategory.objects.get_or_create(
            name="nonexistent_category_test",
            defaults={
                "display_name": "Nonexistent Category",
                "description": "A category with no trust level set",
            },
        )

        trust_level = self.trust_profile.get_trust_level_for_category(category)
        self.assertEqual(trust_level, TrustLevel.UNTRUSTED)

    def test_trust_profile_defaults(self):
        """Test that trust profile has correct default values"""
        self.assertEqual(self.trust_profile.gm_trust_level, TrustLevel.UNTRUSTED)
        self.assertEqual(self.trust_profile.total_positive_feedback, 0)
        self.assertEqual(self.trust_profile.total_negative_feedback, 0)


class FeedbackRatingSystemTestCase(TestCase):
    """Test the feedback rating system functionality"""

    @classmethod
    def setUpTestData(cls):
        cls.story = StoryFactory()
        cls.reviewer = AccountFactory()
        cls.reviewed_player = AccountFactory()
        cls.trust_category1, _ = TrustCategory.objects.get_or_create(
            name="feedback_test1",
            defaults={"display_name": "Test 1", "description": "Test category 1"},
        )
        cls.trust_category2, _ = TrustCategory.objects.get_or_create(
            name="feedback_test2",
            defaults={"display_name": "Test 2", "description": "Test category 2"},
        )

    def test_feedback_average_rating_calculation(self):
        """Test that feedback average rating is calculated correctly"""
        from world.stories.models import StoryFeedback, TrustCategoryFeedbackRating

        # Create feedback
        feedback = StoryFeedback.objects.create(
            story=self.story,
            reviewer=self.reviewer,
            reviewed_player=self.reviewed_player,
            comments="Good performance",
        )

        # Add mixed ratings
        TrustCategoryFeedbackRating.objects.create(
            feedback=feedback,
            trust_category=self.trust_category1,
            rating=2,  # Excellent
        )
        TrustCategoryFeedbackRating.objects.create(
            feedback=feedback, trust_category=self.trust_category2, rating=-1  # Poor
        )

        # Average should be (2 + (-1)) / 2 = 0.5
        self.assertEqual(feedback.get_average_rating(), 0.5)
        self.assertTrue(feedback.is_overall_positive())

        # Test with negative average
        test_category3, _ = TrustCategory.objects.get_or_create(
            name="feedback_test3",
            defaults={"display_name": "Test 3", "description": "Test category 3"},
        )
        TrustCategoryFeedbackRating.objects.create(
            feedback=feedback, trust_category=test_category3, rating=-2  # Very Poor
        )

        # Average should now be (2 + (-1) + (-2)) / 3 = -0.33...
        avg = feedback.get_average_rating()
        self.assertTrue(avg < 0)
        self.assertFalse(feedback.is_overall_positive())
