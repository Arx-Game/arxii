"""FactoryBoy factories for estate models (#1985)."""

from datetime import timedelta

from django.utils import timezone
import factory

from world.character_sheets.factories import CharacterSheetFactory
from world.estates.constants import BequestKind
from world.estates.models import (
    Bequest,
    EstateClaim,
    EstateConfig,
    EstateSettlement,
    Will,
    WillExecutor,
)
from world.items.factories import ItemInstanceFactory
from world.scenes.factories import PersonaFactory


class WillFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Will

    character_sheet = factory.SubFactory(CharacterSheetFactory)
    testament_text = "PLACEHOLDER testament prose."


class WillExecutorFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = WillExecutor

    will = factory.SubFactory(WillFactory)
    persona = factory.SubFactory(PersonaFactory)


class BequestFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Bequest

    will = factory.SubFactory(WillFactory)
    kind = BequestKind.RESIDUARY
    recipient_persona = factory.SubFactory(PersonaFactory)


class EstateSettlementFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = EstateSettlement

    character_sheet = factory.SubFactory(CharacterSheetFactory)
    deadline = factory.LazyFunction(lambda: timezone.now() + timedelta(days=14))


class EstateClaimFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = EstateClaim

    settlement = factory.SubFactory(EstateSettlementFactory)
    item = factory.SubFactory(ItemInstanceFactory)
    claimant_persona = factory.SubFactory(PersonaFactory)


class EstateConfigFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = EstateConfig
