"""Tests for CharacterPathHistory model."""

from django.contrib.admin.sites import site as admin_site
from django.db import IntegrityError
from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.classes.factories import PathFactory
from world.classes.models import PathStage
from world.progression.factories import CharacterPathHistoryFactory
from world.progression.models import CharacterPathHistory


class CharacterPathHistoryTest(TestCase):
    """Tests for CharacterPathHistory model."""

    @classmethod
    def setUpTestData(cls):
        cls.character = CharacterFactory()
        cls.steel = PathFactory(name="Path of Steel", stage=PathStage.PROSPECT, minimum_level=1)
        cls.vanguard = PathFactory(name="Vanguard", stage=PathStage.POTENTIAL, minimum_level=3)

    def test_create_path_history(self):
        """Can create a path history record."""
        history = CharacterPathHistory.objects.create(
            character=self.character,
            path=self.steel,
        )
        self.assertEqual(history.character, self.character)
        self.assertEqual(history.path, self.steel)
        self.assertIsNotNone(history.selected_at)

    def test_path_history_unique_constraint(self):
        """Cannot add same path twice to same character."""
        CharacterPathHistory.objects.create(character=self.character, path=self.steel)
        with self.assertRaises(IntegrityError):
            CharacterPathHistory.objects.create(character=self.character, path=self.steel)

    def test_character_can_have_multiple_paths(self):
        """Character can have paths from different stages."""
        CharacterPathHistory.objects.create(character=self.character, path=self.steel)
        CharacterPathHistory.objects.create(character=self.character, path=self.vanguard)

        self.assertEqual(self.character.path_history.count(), 2)

    def test_path_history_ordering(self):
        """Path history ordered by stage."""
        CharacterPathHistory.objects.create(character=self.character, path=self.vanguard)
        CharacterPathHistory.objects.create(character=self.character, path=self.steel)

        paths = list(self.character.path_history.all())
        self.assertEqual(paths[0].path.stage, PathStage.PROSPECT)
        self.assertEqual(paths[1].path.stage, PathStage.POTENTIAL)


class CharacterPathHistoryAdminTest(TestCase):
    """Tests for CharacterPathHistory admin."""

    def test_registered_in_admin(self):
        """CharacterPathHistory is registered in admin."""
        self.assertIn(CharacterPathHistory, admin_site._registry)


class CharacterPathHistoryFactoryTest(TestCase):
    """Tests for CharacterPathHistory factory."""

    def test_factory_creates_valid_record(self):
        """Factory creates a valid path history record."""
        history = CharacterPathHistoryFactory()
        self.assertIsNotNone(history.character)
        self.assertIsNotNone(history.path)
        self.assertIsNotNone(history.selected_at)
