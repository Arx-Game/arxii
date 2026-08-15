from __future__ import annotations

import factory
import factory.django as factory_django

from world.character_sheets.factories import CharacterSheetFactory
from world.locations.constants import LocationParentType
from world.narrative.constants import ConditionType, NarrativeCategory
from world.narrative.models import (
    AmbientEmit,
    AmbientEmoteCondition,
    AmbientEmoteLine,
    Gemit,
    NarrativeMessage,
    NarrativeMessageDelivery,
    UserStoryMute,
)


class NarrativeMessageFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = NarrativeMessage

    body = factory.Faker("paragraph")
    ooc_note = ""
    category = NarrativeCategory.STORY
    sender_account = None
    related_story = None
    related_beat_completion = None
    related_episode_resolution = None


class NarrativeMessageDeliveryFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = NarrativeMessageDelivery

    message = factory.SubFactory(NarrativeMessageFactory)
    recipient_character_sheet = factory.SubFactory(CharacterSheetFactory)
    delivered_at = None
    acknowledged_at = None


class GemitFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = Gemit

    body = factory.Faker("paragraph")
    sender_account = None
    related_era = None
    related_story = None


class UserStoryMuteFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = UserStoryMute

    account = factory.SubFactory("evennia_extensions.factories.AccountFactory")
    story = factory.SubFactory("world.stories.factories.StoryFactory")


class AmbientEmoteLineFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = AmbientEmoteLine

    parent_type = LocationParentType.ROOM
    room_profile = factory.SubFactory("evennia_extensions.factories.RoomProfileFactory")
    area = None
    arriver_body = factory.Sequence(lambda n: f"PLACEHOLDER ambient line {n}")
    weight = 1
    fire_chance = 100
    cooldown_minutes = 0
    is_active = True


class AmbientEmoteConditionFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = AmbientEmoteCondition

    line = factory.SubFactory(AmbientEmoteLineFactory)
    condition_type = ConditionType.SPECIES
    species = factory.SubFactory("world.species.factories.SpeciesFactory")


class AmbientEmitFactory(factory_django.DjangoModelFactory):
    """PLACEHOLDER ambient texture rows for tests (#2988) — never committed as fixtures.

    Defaults every season/phase flag True (always time-eligible) and no scope/gate, so a
    test only sets the axis it's actually exercising.
    """

    class Meta:
        model = AmbientEmit

    text = factory.Sequence(lambda n: f"PLACEHOLDER ambient texture line {n}")
    weight = 1
    cooldown_minutes = 0
    area = None
    room_profile = None
    gate_stat_key = ""
    gate_min = None
    gate_max = None
    in_spring = True
    in_summer = True
    in_autumn = True
    in_winter = True
    at_dawn = True
    at_day = True
    at_dusk = True
    at_night = True
