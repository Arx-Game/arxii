"""
Factory definitions for character creation system tests.
"""

import factory
import factory.django as factory_django

from world.character_creation.constants import ApplicationStatus, CommentType
from world.character_creation.models import (
    Beginnings,
    BeginningTradition,
    CharacterDraft,
    DraftApplication,
    DraftApplicationComment,
    OriginTemplate,
    OriginTemplateSlot,
    OriginTemplateSlotChoice,
    StartingArea,
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
    minimum_trust = 0


class BeginningsFactory(factory_django.DjangoModelFactory):
    """Factory for creating Beginnings instances."""

    class Meta:
        model = Beginnings

    name = factory.Sequence(lambda n: f"TestBeginnings{n}")
    description = factory.LazyAttribute(lambda obj: f"Description of {obj.name}")
    starting_area = factory.SubFactory(StartingAreaFactory)
    is_active = True
    trust_required = 0
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
    named_family_kind = factory.SubFactory(FamilyKindFactory, name=COMMONER_KIND_NAME)

    @factory.post_generation
    def family_templates(self, create, extracted, **kwargs):
        if create and extracted:
            self.family_templates.set(extracted)


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

    slot = factory.SubFactory(OriginTemplateSlotFactory, allows_text=False)
    name = factory.Sequence(lambda n: f"Choice {n}")
    sort_order = factory.Sequence(lambda n: n)


def make_unknown_upbringing(beginning: Beginnings) -> OriginTemplate:
    """The amnesiac shape: one 'Unknown' Upbringing, none path, no prompts (#3617)."""
    return OriginTemplateFactory(
        beginning=beginning,
        name="Unknown",
        frame_narrative="You have no past you can speak of.",
        allows_name_family=False,
        named_family_kind=None,
        allows_no_family=True,
    )
