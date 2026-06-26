"""Shared test utilities for the actions app."""

from django.test import TestCase
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper import models as idmapper_models

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
        """Create fresh ObjectDB/CharacterSheet instances for each test.

        Evennia ObjectDB/typeclass instances are not deepcopy-safe in Django's
        setUpTestData, so character data is rebuilt per-test. Shared fixtures
        that do not hold ObjectDB state can live in setUpTestData().
        """
        idmapper_models.flush_cache()
        self.actor = CharacterFactory()
        self.actor_sheet = CharacterSheetFactory(character=self.actor)
        self.target = CharacterFactory()
        self.target_sheet = CharacterSheetFactory(character=self.target)
