"""Factory definitions for the vitals system tests."""

from __future__ import annotations

import factory
import factory.django as factory_django

from world.character_sheets.factories import CharacterSheetFactory
from world.vitals.constants import CharacterLifeState
from world.vitals.models import CharacterVitals


class CharacterVitalsFactory(factory_django.DjangoModelFactory):
    """Factory for creating CharacterVitals instances."""

    class Meta:
        model = CharacterVitals
        django_get_or_create = ("character_sheet",)

    character_sheet = factory.SubFactory(CharacterSheetFactory)
    life_state = CharacterLifeState.ALIVE
    health = 100
    max_health = 100
    base_max_health = 100
