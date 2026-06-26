"""Shared test utilities for the actions app."""

from django.test import TestCase
from evennia.objects.models import ObjectDB

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import CharacterSheet


class ActionTestCase(TestCase):
    """Base test case that provides an actor with a sheet and a target sheet."""

    actor: ObjectDB
    actor_sheet: CharacterSheet
    target: ObjectDB
    target_sheet: CharacterSheet

    @classmethod
    def setUpTestData(cls) -> None:
        cls.actor = CharacterFactory()
        cls.actor_sheet = CharacterSheetFactory(character=cls.actor)
        cls.target = CharacterFactory()
        cls.target_sheet = CharacterSheetFactory(character=cls.target)
