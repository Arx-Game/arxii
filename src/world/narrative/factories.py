from __future__ import annotations

import factory
import factory.django as factory_django

from world.character_sheets.factories import CharacterSheetFactory
from world.narrative.constants import NarrativeCategory
from world.narrative.models import NarrativeMessage, NarrativeMessageDelivery


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
