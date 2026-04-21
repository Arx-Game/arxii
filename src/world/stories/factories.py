import factory
import factory.django as factory_django
import factory.fuzzy

from world.stories.constants import (
    BeatOutcome,
    BeatPredicateType,
    BeatVisibility,
    EraStatus,
    StoryScope,
    TransitionMode,
)
from world.stories.models import (
    Beat,
    Chapter,
    Episode,
    EpisodeScene,
    Era,
    PlayerTrust,
    PlayerTrustLevel,
    Story,
    StoryFeedback,
    StoryParticipation,
    Transition,
    TrustCategory,
    TrustCategoryFeedbackRating,
)
from world.stories.types import (
    ParticipationLevel,
    StoryPrivacy,
    StoryStatus,
    TrustLevel,
)


class EraFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = Era
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"era_{n}")
    display_name = factory.Sequence(lambda n: f"Era {n}")
    season_number = factory.Sequence(lambda n: n + 1)
    status = EraStatus.UPCOMING


class StoryFactory(factory_django.DjangoModelFactory):
    """Factory for creating Story instances"""

    class Meta:
        model = Story

    title = factory.Faker("sentence", nb_words=4)
    description = factory.Faker("paragraph", nb_sentences=3)
    status = StoryStatus.ACTIVE
    privacy = StoryPrivacy.PUBLIC
    scope = StoryScope.CHARACTER
    character_sheet = None  # Tests that need character-scoped stories set this explicitly.
    created_in_era = None
    is_personal_story = False
    personal_story_character = None

    @factory.post_generation
    def owners(self, create, extracted, **kwargs):
        """Add owners to the story"""
        if not create:
            return

        if extracted:
            for owner in extracted:
                self.owners.add(owner)

    @factory.post_generation
    def active_gms(self, create, extracted, **kwargs):
        """Add active GMs to the story"""
        if not create:
            return

        if extracted:
            for gm in extracted:
                self.active_gms.add(gm)


class PersonalStoryFactory(StoryFactory):
    """Factory for creating personal stories"""

    is_personal_story = True
    # Note: personal_story_character must be set manually due to cross-app
    # dependencies
    personal_story_character = None


class PrivateStoryFactory(StoryFactory):
    """Factory for creating private stories"""

    privacy = StoryPrivacy.PRIVATE


class StoryParticipationFactory(factory_django.DjangoModelFactory):
    """Factory for creating StoryParticipation instances"""

    class Meta:
        model = StoryParticipation

    story = factory.SubFactory(StoryFactory)
    # Note: character must be set manually due to cross-app dependencies
    participation_level = ParticipationLevel.OPTIONAL
    trusted_by_owner = False
    is_active = True


class CriticalParticipationFactory(StoryParticipationFactory):
    """Factory for critical story participation"""

    participation_level = ParticipationLevel.CRITICAL
    trusted_by_owner = True


class ChapterFactory(factory_django.DjangoModelFactory):
    """Factory for creating Chapter instances"""

    class Meta:
        model = Chapter

    story = factory.SubFactory(StoryFactory)
    title = factory.Faker("sentence", nb_words=3)
    description = factory.Faker("paragraph", nb_sentences=2)
    order = factory.Sequence(lambda n: n + 1)
    is_active = False
    summary = factory.Faker("paragraph", nb_sentences=2)
    consequences = factory.Faker("paragraph", nb_sentences=1)


class ActiveChapterFactory(ChapterFactory):
    """Factory for creating active chapters"""

    is_active = True


class EpisodeFactory(factory_django.DjangoModelFactory):
    """Factory for creating Episode instances"""

    class Meta:
        model = Episode

    chapter = factory.SubFactory(ChapterFactory)
    title = factory.Faker("sentence", nb_words=3)
    description = factory.Faker("paragraph", nb_sentences=2)
    order = factory.Sequence(lambda n: n + 1)
    is_active = False
    summary = factory.Faker("paragraph", nb_sentences=2)
    consequences = factory.Faker("paragraph", nb_sentences=1)


class ActiveEpisodeFactory(EpisodeFactory):
    """Factory for creating active episodes"""

    is_active = True


class EpisodeWithButConnectionFactory(EpisodeFactory):
    """Factory for episodes with 'but' connection — kept for scenario variety"""


class TransitionFactory(factory_django.DjangoModelFactory):
    """Factory for creating Transition instances linking two Episodes."""

    class Meta:
        model = Transition

    source_episode = factory.SubFactory(EpisodeFactory)
    target_episode = factory.LazyAttribute(
        lambda obj: EpisodeFactory(chapter=obj.source_episode.chapter)
    )
    mode = TransitionMode.AUTO
    order = 0


# Note: SceneFactory removed due to cross-app dependency issues
# Create Scene instances directly in tests when needed


class EpisodeSceneFactory(factory_django.DjangoModelFactory):
    """Factory for creating EpisodeScene connections"""

    class Meta:
        model = EpisodeScene

    episode = factory.SubFactory(EpisodeFactory)
    # Note: scene field must be set manually when creating instances
    # due to cross-app dependency issues with SceneFactory
    order = factory.Sequence(lambda n: n + 1)


class PlayerTrustFactory(factory_django.DjangoModelFactory):
    """Factory for creating PlayerTrust instances"""

    class Meta:
        model = PlayerTrust

    # Note: account must be set manually due to cross-app dependencies
    gm_trust_level = TrustLevel.UNTRUSTED


class TrustedPlayerTrustFactory(PlayerTrustFactory):
    """Factory for players with higher trust levels"""

    gm_trust_level = TrustLevel.BASIC


class ExperiencedGMTrustFactory(PlayerTrustFactory):
    """Factory for experienced GM trust profiles"""

    gm_trust_level = TrustLevel.ADVANCED


class PlayerTrustLevelFactory(factory_django.DjangoModelFactory):
    """Factory for creating PlayerTrustLevel instances"""

    class Meta:
        model = PlayerTrustLevel

    player_trust = factory.SubFactory(PlayerTrustFactory)
    trust_category = factory.SubFactory("world.stories.factories.TrustCategoryFactory")
    trust_level = TrustLevel.BASIC
    positive_feedback_count = 0
    negative_feedback_count = 0
    notes = factory.Faker("sentence")


class TrustCategoryFactory(factory_django.DjangoModelFactory):
    """Factory for creating TrustCategory instances"""

    class Meta:
        model = TrustCategory

    name = factory.Sequence(lambda n: f"trust_category_{n}")
    display_name = factory.Faker("sentence", nb_words=2)
    description = factory.Faker("paragraph", nb_sentences=2)
    is_active = True


class TrustCategoryFeedbackRatingFactory(factory_django.DjangoModelFactory):
    """Factory for creating TrustCategoryFeedbackRating instances"""

    class Meta:
        model = TrustCategoryFeedbackRating

    feedback = factory.SubFactory("world.stories.factories.StoryFeedbackFactory")
    trust_category = factory.SubFactory(TrustCategoryFactory)
    rating = 1  # Default to "Good"
    notes = factory.Faker("sentence")


class StoryFeedbackFactory(factory_django.DjangoModelFactory):
    """Factory for creating StoryFeedback instances"""

    class Meta:
        model = StoryFeedback

    story = factory.SubFactory(StoryFactory)
    # Note: reviewer and reviewed_player must be set manually due to
    # cross-app dependencies
    is_gm_feedback = False
    comments = factory.Faker("paragraph", nb_sentences=3)


class PositiveFeedbackFactory(StoryFeedbackFactory):
    """Factory for creating positive feedback with good ratings"""

    @factory.post_generation
    def category_ratings(self, create, extracted, **kwargs):
        """Add positive ratings for trust categories"""
        if not create:
            return

        categories = extracted or [TrustCategoryFactory()]
        for category in categories:
            TrustCategoryFeedbackRatingFactory(
                feedback=self,
                trust_category=category,
                rating=factory.fuzzy.FuzzyChoice([1, 2]),  # Good to Excellent
            )


class NegativeFeedbackFactory(StoryFeedbackFactory):
    """Factory for creating negative feedback with poor ratings"""

    comments = factory.Faker(
        "paragraph",
        nb_sentences=3,
        extra_kwargs={"start_words": ["Unfortunately", "Sadly", "Regrettably"]},
    )

    @factory.post_generation
    def category_ratings(self, create, extracted, **kwargs):
        """Add negative ratings for trust categories"""
        if not create:
            return

        categories = extracted or [TrustCategoryFactory()]
        for category in categories:
            TrustCategoryFeedbackRatingFactory(
                feedback=self,
                trust_category=category,
                rating=factory.fuzzy.FuzzyChoice([-2, -1]),  # Poor to Very Poor
            )


class GMFeedbackFactory(StoryFeedbackFactory):
    """Factory for creating GM-specific feedback"""

    is_gm_feedback = True
    comments = factory.Faker(
        "paragraph",
        nb_sentences=3,
        extra_kwargs={"start_words": ["The GM", "Game Master", "As a GM"]},
    )


class BeatFactory(factory_django.DjangoModelFactory):
    """Factory for creating Beat instances"""

    class Meta:
        model = Beat

    episode = factory.SubFactory(EpisodeFactory)
    predicate_type = BeatPredicateType.GM_MARKED
    outcome = BeatOutcome.UNSATISFIED
    visibility = BeatVisibility.HINTED
    internal_description = factory.Faker("sentence")
    player_hint = factory.Faker("sentence")
    player_resolution_text = factory.Faker("sentence")
    required_level = None


# Convenience functions for common test scenarios


def create_complete_story_structure():
    """Create a complete story with chapters and episodes"""
    # Note: Scenes omitted due to cross-app dependencies
    story = StoryFactory()

    # Create 2 chapters
    chapter1 = ChapterFactory(story=story, order=1, is_active=True)
    chapter2 = ChapterFactory(story=story, order=2)

    # Create episodes for first chapter
    EpisodeFactory(chapter=chapter1, order=1, is_active=True)
    EpisodeFactory(chapter=chapter1, order=2)

    # Create episodes for second chapter
    EpisodeFactory(chapter=chapter2, order=1)

    # Note: Scene creation and EpisodeScene connections omitted
    # due to cross-app dependency issues. Create manually in tests if needed.

    return story


def create_story_with_participants():
    """Create a story with multiple participants at different levels"""
    # Note: This function requires manual character creation due to
    # cross-app dependencies. Characters must be created manually in tests
    # using evennia_extensions.factories
    return StoryFactory()


def create_story_with_feedback():
    """Create a story with various types of feedback"""
    # Note: This function requires manual account creation due to
    # cross-app dependencies. Accounts must be created manually in tests
    # using evennia_extensions.factories
    return StoryFactory()
