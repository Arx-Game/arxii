from django.test import TestCase

from evennia_extensions.factories import (
    AccountFactory,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMProfileFactory
from world.stories.constants import StoryScope
from world.stories.factories import (
    ChapterFactory,
    EpisodeFactory,
    PersonalStoryFactory,
    StoryFactory,
    StoryParticipationFactory,
)
from world.stories.models import (
    Chapter,
    Episode,
    TrustCategory,
)
from world.stories.types import (
    ParticipationLevel,
    StoryPrivacy,
    StoryStatus,
)


class StoryModelTestCase(TestCase):
    """Test Story model methods and properties"""

    @classmethod
    def setUpTestData(cls):
        """Create test data once for the entire test class"""
        cls.user = AccountFactory()
        cls.story = StoryFactory()
        cls.private_story = StoryFactory(privacy=StoryPrivacy.PRIVATE)
        # PersonalStoryFactory is a CHARACTER-scope story; no legacy fields.
        cls.personal_story = PersonalStoryFactory()

    def test_is_active_returns_false_without_gms(self):
        """Test that stories without active GMs are not considered active"""
        self.story.status = StoryStatus.ACTIVE
        self.story.save()
        assert not self.story.is_active()

    def test_is_active_returns_true_with_gms(self):
        """Test that stories with active GMs and active status are active"""

        gm_profile = GMProfileFactory()

        self.story.status = StoryStatus.ACTIVE
        self.story.active_gms.add(gm_profile)
        self.story.save()

        assert self.story.is_active()

    def test_can_player_apply_to_public_story(self):
        """Test that players can apply to public stories"""
        assert self.story.can_player_apply(self.user)

    def test_cannot_player_apply_to_private_story(self):
        """Test that players cannot apply to private stories by default"""
        assert not self.private_story.can_player_apply(self.user)

    def test_personal_story_has_character_scope(self):
        """CHARACTER-scope stories created via PersonalStoryFactory have scope=CHARACTER."""
        assert self.personal_story.scope == StoryScope.CHARACTER

    def test_owner_account_ids_caches_and_invalidates(self):
        """owner_account_ids is identity-map cached; invalidate_owner_cache
        clears it so a subsequent read reflects an owners mutation."""
        # Fresh local instance (cls.story is shared across tests).
        account = AccountFactory()
        story = StoryFactory()

        # First access populates the cache (empty — no owners yet).
        assert story.owner_account_ids == frozenset()

        story.owners.add(account)
        # Still stale: the cached_property was not invalidated.
        assert story.owner_account_ids == frozenset()

        story.invalidate_owner_cache()
        # Now reflects the mutation.
        assert story.owner_account_ids == frozenset({account.pk})


class StoryParticipationModelTestCase(TestCase):
    """Test StoryParticipation model methods"""

    @classmethod
    def setUpTestData(cls):
        """Create test data once for the entire test class"""
        cls.story = StoryFactory()
        cls.character = CharacterSheetFactory().character
        cls.participation = StoryParticipationFactory(
            story=cls.story,
            character=cls.character.sheet_data,
        )

    def test_participation_defaults(self):
        """Test that participation has correct default values"""
        assert self.participation.participation_level == ParticipationLevel.OPTIONAL
        assert not self.participation.trusted_by_owner
        assert self.participation.is_active


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

        assert list(chapters) == [self.chapter, chapter2]


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

        assert list(episodes) == [self.episode, episode2]


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
            feedback=feedback,
            trust_category=self.trust_category2,
            rating=-1,  # Poor
        )

        # Average should be (2 + (-1)) / 2 = 0.5
        assert feedback.get_average_rating() == 0.5
        assert feedback.is_overall_positive()

        # Test with negative average
        test_category3, _ = TrustCategory.objects.get_or_create(
            name="feedback_test3",
            defaults={"display_name": "Test 3", "description": "Test category 3"},
        )
        TrustCategoryFeedbackRating.objects.create(
            feedback=feedback,
            trust_category=test_category3,
            rating=-2,  # Very Poor
        )

        # Average should now be (2 + (-1) + (-2)) / 3 = -0.33...
        avg = feedback.get_average_rating()
        assert avg < 0
        assert not feedback.is_overall_positive()


class StoryPrimaryTableTest(TestCase):
    def test_primary_table_default_null(self) -> None:
        from world.stories.factories import StoryFactory

        story = StoryFactory()
        assert story.primary_table is None

    def test_primary_table_can_be_set(self) -> None:
        from world.gm.factories import GMTableFactory
        from world.stories.factories import StoryFactory

        table = GMTableFactory()
        story = StoryFactory(primary_table=table)
        assert story.primary_table == table
        assert story in table.primary_stories.all()

    def test_primary_table_set_null_on_table_delete(self) -> None:
        from world.gm.factories import GMTableFactory
        from world.stories.factories import StoryFactory
        from world.stories.models import Story

        table = GMTableFactory()
        story = StoryFactory(primary_table=table)
        table.delete()
        # Flush identity mapper cache so refresh_from_db picks up SET_NULL change
        Story.flush_instance_cache()
        story.refresh_from_db()
        assert story.primary_table is None
