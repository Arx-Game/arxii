import factory
import factory.django as factory_django
import factory.fuzzy

from world.character_sheets.factories import CharacterSheetFactory
from world.stories.constants import (
    AssistantClaimStatus,
    BeatOutcome,
    BeatPredicateType,
    BeatVisibility,
    EraStatus,
    SessionRequestStatus,
    StoryGMOfferStatus,
    StoryScope,
    TransitionMode,
)
from world.stories.models import (
    AggregateBeatContribution,
    AssistantGMClaim,
    Beat,
    BeatCompletion,
    Chapter,
    Episode,
    EpisodeProgressionRequirement,
    EpisodeResolution,
    EpisodeScene,
    Era,
    GlobalStoryProgress,
    GroupStoryProgress,
    PlayerTrust,
    PlayerTrustLevel,
    SessionRequest,
    Story,
    StoryFeedback,
    StoryGMOffer,
    StoryParticipation,
    StoryProgress,
    TableBulletinPost,
    TableBulletinReply,
    Transition,
    TransitionRequiredOutcome,
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
    """Factory for creating CHARACTER-scope stories (personal arcs).

    scope=CHARACTER is already the StoryFactory default; this subclass exists
    as a named alias for tests that historically referenced PersonalStoryFactory.
    Set character_sheet explicitly when a FK to CharacterSheet is needed.
    """


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
    required_achievement = None
    required_condition_template = None
    required_codex_entry = None
    referenced_story = None
    referenced_milestone_type = ""
    referenced_chapter = None
    referenced_episode = None
    required_points = None


class EpisodeProgressionRequirementFactory(factory_django.DjangoModelFactory):
    """Factory for creating EpisodeProgressionRequirement instances."""

    class Meta:
        model = EpisodeProgressionRequirement

    episode = factory.SubFactory(EpisodeFactory)
    beat = factory.LazyAttribute(lambda obj: BeatFactory(episode=obj.episode))
    required_outcome = BeatOutcome.SUCCESS


class TransitionRequiredOutcomeFactory(factory_django.DjangoModelFactory):
    """Factory for creating TransitionRequiredOutcome instances."""

    class Meta:
        model = TransitionRequiredOutcome

    transition = factory.SubFactory(TransitionFactory)
    beat = factory.LazyAttribute(lambda obj: BeatFactory(episode=obj.transition.source_episode))
    required_outcome = BeatOutcome.SUCCESS


class BeatCompletionFactory(factory_django.DjangoModelFactory):
    """Factory for creating BeatCompletion audit ledger entries.

    Defaults to CHARACTER-scope (character_sheet populated, gm_table null).
    For GROUP-scope completions override beat and set gm_table; for GLOBAL-scope
    override beat and leave both character_sheet and gm_table as None.
    """

    class Meta:
        model = BeatCompletion

    beat = factory.SubFactory(BeatFactory)
    character_sheet = factory.SubFactory(CharacterSheetFactory)
    gm_table = None
    roster_entry = None
    era = None
    outcome = BeatOutcome.SUCCESS
    gm_notes = ""


class AggregateBeatContributionFactory(factory_django.DjangoModelFactory):
    """Factory for creating AggregateBeatContribution ledger rows."""

    class Meta:
        model = AggregateBeatContribution

    beat = factory.SubFactory(BeatFactory)
    character_sheet = factory.SubFactory(CharacterSheetFactory)
    roster_entry = None
    era = None
    points = 10
    source_note = factory.Faker("sentence")


class EpisodeResolutionFactory(factory_django.DjangoModelFactory):
    """Factory for creating EpisodeResolution audit ledger entries.

    Defaults to a CHARACTER-scope episode/story with character_sheet populated.
    For GROUP or GLOBAL scope tests, override episode and set the appropriate FK.
    """

    class Meta:
        model = EpisodeResolution

    episode = factory.SubFactory(EpisodeFactory)
    character_sheet = factory.SubFactory(CharacterSheetFactory)
    gm_table = None
    chosen_transition = None
    resolved_by = None
    era = None
    gm_notes = ""


class StoryProgressFactory(factory_django.DjangoModelFactory):
    """Factory for creating StoryProgress per-character progress pointer instances."""

    class Meta:
        model = StoryProgress

    story = factory.SubFactory(StoryFactory)
    character_sheet = factory.SubFactory(CharacterSheetFactory)
    current_episode = None
    is_active = True


class GroupStoryProgressFactory(factory_django.DjangoModelFactory):
    """Factory for creating GroupStoryProgress per-group progress pointer instances."""

    class Meta:
        model = GroupStoryProgress

    story = factory.SubFactory(StoryFactory, scope=StoryScope.GROUP)
    gm_table = factory.SubFactory("world.gm.factories.GMTableFactory")
    current_episode = None
    is_active = True


class GlobalStoryProgressFactory(factory_django.DjangoModelFactory):
    """Factory for creating GlobalStoryProgress singleton-per-story progress instances."""

    class Meta:
        model = GlobalStoryProgress

    story = factory.SubFactory(StoryFactory, scope=StoryScope.GLOBAL)
    current_episode = None
    is_active = True


class AssistantGMClaimFactory(factory_django.DjangoModelFactory):
    """Factory for creating AssistantGMClaim instances."""

    class Meta:
        model = AssistantGMClaim

    beat = factory.SubFactory(
        BeatFactory, agm_eligible=True, predicate_type=BeatPredicateType.GM_MARKED
    )
    assistant_gm = factory.SubFactory("world.gm.factories.GMProfileFactory")
    status = AssistantClaimStatus.REQUESTED
    approved_by = None
    rejection_note = ""
    framing_note = factory.Faker("paragraph")


class StoryGMOfferFactory(factory_django.DjangoModelFactory):
    """Factory for creating StoryGMOffer instances.

    Defaults to PENDING status. For accepted/declined/withdrawn offers, pass
    status=StoryGMOfferStatus.ACCEPTED etc. and set responded_at manually.
    """

    class Meta:
        model = StoryGMOffer

    story = factory.SubFactory(StoryFactory, scope=StoryScope.CHARACTER, primary_table=None)
    offered_to = factory.SubFactory("world.gm.factories.GMProfileFactory")
    offered_by_account = factory.SubFactory("evennia_extensions.factories.AccountFactory")
    status = StoryGMOfferStatus.PENDING
    message = ""
    response_note = ""
    responded_at = None


class SessionRequestFactory(factory_django.DjangoModelFactory):
    """Factory for creating SessionRequest instances."""

    class Meta:
        model = SessionRequest

    episode = factory.SubFactory(EpisodeFactory)
    status = SessionRequestStatus.OPEN
    event = None
    open_to_any_gm = False
    assigned_gm = None
    initiated_by_account = None
    notes = ""


# ---------------------------------------------------------------------------
# Wave 10: Bulletin factories
# ---------------------------------------------------------------------------


class TableBulletinPostFactory(factory_django.DjangoModelFactory):
    """Factory for TableBulletinPost — defaults to a table-wide post (story=None)."""

    class Meta:
        model = TableBulletinPost

    table = factory.SubFactory("world.gm.factories.GMTableFactory")
    story = None
    author_persona = factory.SubFactory("world.scenes.factories.PersonaFactory")
    title = factory.Faker("sentence", nb_words=5)
    body = factory.Faker("paragraph", nb_sentences=3)
    allow_replies = True


class TableBulletinReplyFactory(factory_django.DjangoModelFactory):
    """Factory for TableBulletinReply."""

    class Meta:
        model = TableBulletinReply

    post = factory.SubFactory(TableBulletinPostFactory)
    author_persona = factory.SubFactory("world.scenes.factories.PersonaFactory")
    body = factory.Faker("paragraph", nb_sentences=2)


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
