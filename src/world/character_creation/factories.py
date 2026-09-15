"""
Factory definitions for character creation system tests.
"""

import factory
import factory.django as factory_django

from world.character_creation.constants import (
    AnchorSource,
    ApplicationStatus,
    CommentType,
    ConnectionKind,
    LifeStage,
    OfferArrival,
    OfferChapter,
    QuestionKind,
    TraditionState,
)
from world.character_creation.models import (
    AppearanceSection,
    Beginnings,
    BeginningTradition,
    CharacterDraft,
    DistinctionOffer,
    DraftApplication,
    DraftApplicationComment,
    EnemyReason,
    OfferFirstLook,
    OriginTemplate,
    OriginTemplateSlot,
    OriginTemplateSlotChoice,
    SchoolingLine,
    StartingArea,
    TraditionStateLine,
)
from world.realms.models import Realm
from world.roster.constants import COMMONER_KIND_NAME
from world.roster.factories import FamilyKindFactory


class RealmFactory(factory_django.DjangoModelFactory):
    """Factory for creating Realm instances."""

    class Meta:
        model = Realm
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"TestRealm{n}")
    description = factory.LazyAttribute(lambda obj: f"Description of {obj.name}")


class StartingAreaFactory(factory_django.DjangoModelFactory):
    """Factory for creating StartingArea instances."""

    class Meta:
        model = StartingArea
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"TestArea{n}")
    description = factory.LazyAttribute(lambda obj: f"Description of {obj.name}")
    realm = factory.SubFactory(RealmFactory)
    is_active = True
    access_level = StartingArea.AccessLevel.ALL


class BeginningsFactory(factory_django.DjangoModelFactory):
    """Factory for creating Beginnings instances."""

    class Meta:
        model = Beginnings

    name = factory.Sequence(lambda n: f"TestBeginnings{n}")
    description = factory.LazyAttribute(lambda obj: f"Description of {obj.name}")
    starting_area = factory.SubFactory(StartingAreaFactory)
    is_active = True
    grants_species_languages = True
    sort_order = 0
    cg_point_cost = 0
    social_rank = 0


class CharacterDraftFactory(factory_django.DjangoModelFactory):
    """Factory for creating CharacterDraft instances."""

    class Meta:
        model = CharacterDraft

    account = factory.SubFactory("evennia_extensions.factories.AccountFactory")
    selected_area = factory.SubFactory(StartingAreaFactory)
    current_stage = CharacterDraft.Stage.ORIGIN

    # Stage 2: Heritage
    selected_beginnings = None  # Optional, set in tests as needed

    # Stage 5: Path
    selected_path = None  # Optional, set in tests as needed

    # Stage 7: Appearance fields (default to None)
    height_band = None
    height_inches = None
    build = None


class DraftApplicationFactory(factory_django.DjangoModelFactory):
    """Factory for DraftApplication instances."""

    class Meta:
        model = DraftApplication

    draft = factory.SubFactory(CharacterDraftFactory)
    status = ApplicationStatus.SUBMITTED
    submission_notes = "I'd like to play this character."


class DraftApplicationCommentFactory(factory_django.DjangoModelFactory):
    """Factory for DraftApplicationComment instances."""

    class Meta:
        model = DraftApplicationComment

    application = factory.SubFactory(DraftApplicationFactory)
    author = factory.SubFactory("evennia_extensions.factories.AccountFactory")
    text = "This is a comment."
    comment_type = CommentType.MESSAGE


class BeginningTraditionFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = BeginningTradition

    beginning = factory.SubFactory(BeginningsFactory)
    tradition = factory.SubFactory("world.magic.factories.TraditionFactory")
    sort_order = 0


class OriginTemplateFactory(factory_django.DjangoModelFactory):
    """An Upbringing (#3617). Defaults to the name-your-own path on the Commoner kind."""

    class Meta:
        model = OriginTemplate

    beginning = factory.SubFactory(BeginningsFactory)
    name = factory.Sequence(lambda n: f"Upbringing {n}")
    frame_narrative = "You were raised somewhere, by someone."
    allows_name_family = True

    @factory.post_generation
    def family_templates(self, create, extracted, **kwargs):
        if not create:
            return
        if extracted:
            self.family_templates.set(extracted)
            return
        if self.allows_name_family:
            from world.societies.houses.factories import HouseTemplateFactory

            self.family_templates.add(
                HouseTemplateFactory(
                    kind=FamilyKindFactory(name=COMMONER_KIND_NAME),
                    realm=self.beginning.starting_area.realm,
                )
            )


class OriginTemplateSlotFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = OriginTemplateSlot

    template = factory.SubFactory(OriginTemplateFactory)
    name = factory.Sequence(lambda n: f"Prompt {n}")
    prompt = "What did your family keep running?"
    sort_order = factory.Sequence(lambda n: n)


class OriginTemplateSlotChoiceFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = OriginTemplateSlotChoice

    slot = factory.SubFactory(OriginTemplateSlotFactory, allows_text=False, kind=QuestionKind.PICK)
    name = factory.Sequence(lambda n: f"Choice {n}")
    sort_order = factory.Sequence(lambda n: n)


class GroupPromptFactory(OriginTemplateSlotFactory):
    """A 'pick a group' question on a LISTED source with no groups yet (#3660)."""

    kind = QuestionKind.GROUP
    anchor_source = AnchorSource.LISTED
    connection_kind = ConnectionKind.RAISED_BY
    life_stage = LifeStage.CHILDHOOD
    allows_text = False


def make_unknown_upbringing(beginning: Beginnings) -> OriginTemplate:
    """The amnesiac shape: one 'Unknown' Upbringing, none path, no prompts (#3617)."""
    return OriginTemplateFactory(
        beginning=beginning,
        name="Unknown",
        frame_narrative="You have no past you can speak of.",
        allows_name_family=False,
        allows_no_family=True,
    )


class TraditionStateLineFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = TraditionStateLine
        django_get_or_create = ("state",)

    state = TraditionState.LIVING_MASTERS
    entry_line = factory.LazyAttribute(lambda o: f"{o.state} line")


class SchoolingLineFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = SchoolingLine
        django_get_or_create = ("rank",)

    rank = 0
    name = factory.LazyAttribute(lambda o: f"Schooling {o.rank}")
    player_line = "A line."


class EnemyReasonFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = EnemyReason

    name = factory.Sequence(lambda n: f"You know what they did {n}")
    player_line = "And they know that you know."


class AppearanceSectionFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = AppearanceSection

    name = factory.Sequence(lambda n: f"Frame {n}")


class DistinctionOfferFactory(factory_django.DjangoModelFactory):
    """An offer line with the opener its chapter wants already set (#3709).

    An Appearance line gets a section and an actor's-sheet line the never-do prompt
    unless the test passes its own, so every chapter's offer is valid out of the box;
    the older chapters' openers (tag, answer, schooling line) are the test's to pass.
    """

    class Meta:
        model = DistinctionOffer

    distinction = factory.SubFactory("world.distinctions.factories.DistinctionFactory")
    chapter = OfferChapter.APPEARANCE
    arrives_as = OfferArrival.CHOICE
    #: Declared so ``appearance_section``'s Maybe can read it (#3739); a test that
    #: wants the feature-rows opener passes ``feature_rows=True``.
    feature_rows = False
    appearance_section = factory.Maybe(
        # An Appearance line is opened by exactly one thing (#3739): a section, or
        # the feature rows. A test that asks for ``feature_rows=True`` gets no
        # section, so the model's own at-most-one-opener rule still holds.
        factory.LazyAttribute(
            lambda o: o.chapter == OfferChapter.APPEARANCE and not o.feature_rows
        ),
        yes_declaration=factory.SubFactory(AppearanceSectionFactory),
        no_declaration=None,
    )
    prompt = factory.LazyAttribute(
        lambda o: "never_do" if o.chapter == OfferChapter.ACTORS_SHEET else ""
    )


class OfferFirstLookFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = OfferFirstLook

    offer = factory.SubFactory(DistinctionOfferFactory)
    beginning = factory.SubFactory(BeginningsFactory)
