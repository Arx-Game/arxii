"""Model tests for the worship foundation (#2355)."""

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.worship.factories import (
    DevotionStandingFactory,
    WorshipDeclarationFactory,
    WorshippedBeingFactory,
    WorshipTraditionFactory,
)


class WorshipModelTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.tradition = WorshipTraditionFactory()
        cls.being = WorshippedBeingFactory(tradition=cls.tradition)
        cls.sheet = CharacterSheetFactory()

    def test_being_defaults(self) -> None:
        self.assertEqual(self.being.resonance_pool, 0)
        self.assertEqual(self.being.lifetime_worship, 0)
        self.assertIsNone(self.being.avatar_sheet)
        self.assertTrue(self.being.is_active)

    def test_devotion_standing_unique_per_sheet_and_being(self) -> None:
        DevotionStandingFactory(character_sheet=self.sheet, being=self.being)
        with transaction.atomic(), self.assertRaises(IntegrityError):
            DevotionStandingFactory(character_sheet=self.sheet, being=self.being)

    def test_declaration_public_only(self) -> None:
        declaration = WorshipDeclarationFactory(character_sheet=self.sheet)
        self.assertIsNotNone(declaration.public_being)
        self.assertIsNone(declaration.secret_being)
        self.assertIsNone(declaration.secret)
