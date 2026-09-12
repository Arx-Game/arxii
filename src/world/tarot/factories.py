"""FactoryBoy factories for tarot models (#3776)."""

import factory

from world.tarot.constants import ArcanaType
from world.tarot.models import TarotCard


class TarotCardFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TarotCard

    name = factory.Sequence(lambda n: f"Tarot Card {n}")
    arcana_type = ArcanaType.MAJOR
    latin_name = factory.Sequence(lambda n: f"Cardus{n}")
    rank = factory.Sequence(lambda n: n)
