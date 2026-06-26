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

    def setUp(self) -> None:
        super().setUp()
        self.actor = CharacterFactory()
        self.actor_sheet = CharacterSheetFactory(character=self.actor)
        self.target = CharacterFactory()
        self.target_sheet = CharacterSheetFactory(character=self.target)
