"""FactoryBoy factories for the captivity system (#931)."""

import factory
from factory.django import DjangoModelFactory

from world.captivity.models import Captivity
from world.character_sheets.factories import CharacterSheetFactory
from world.instances.factories import InstancedRoomFactory


class CaptivityFactory(DjangoModelFactory):
    class Meta:
        model = Captivity

    captive = factory.SubFactory(CharacterSheetFactory)
    cell = factory.SubFactory(InstancedRoomFactory)
