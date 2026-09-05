"""Companion-targeted relationships (#3575): model constraints and display."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.companions.factories import CompanionFactory
from world.relationships.factories import CharacterRelationshipFactory
from world.relationships.models import CharacterRelationship


class CompanionTargetModelTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.owner = CharacterSheetFactory()
        cls.companion = CompanionFactory(owner=cls.owner, name="Ash")

    def test_companion_target_row_saves_and_names_the_companion(self) -> None:
        rel = CharacterRelationshipFactory(
            source=self.owner, target=None, target_companion=self.companion
        )
        self.assertIsNone(rel.target)
        self.assertEqual(rel.target_companion, self.companion)
        self.assertEqual(rel.target_name, "Ash")
        self.assertIn("Ash", str(rel))

    def test_sheet_target_name_is_the_character_key(self) -> None:
        rel = CharacterRelationshipFactory(source=self.owner)
        self.assertEqual(rel.target_name, rel.target.character.db_key)

    def test_clean_rejects_both_targets(self) -> None:
        other = CharacterSheetFactory()
        rel = CharacterRelationship(
            source=self.owner, target=other, target_companion=self.companion
        )
        with self.assertRaises(ValidationError):
            rel.clean()

    def test_clean_rejects_no_target(self) -> None:
        rel = CharacterRelationship(source=self.owner)
        with self.assertRaises(ValidationError):
            rel.clean()

    def test_db_rejects_both_targets(self) -> None:
        other = CharacterSheetFactory()
        with self.assertRaises(IntegrityError), transaction.atomic():
            CharacterRelationship.objects.create(
                source=self.owner, target=other, target_companion=self.companion
            )

    def test_db_rejects_no_target(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            CharacterRelationship.objects.create(source=self.owner)

    def test_one_row_per_companion_per_source(self) -> None:
        CharacterRelationshipFactory(
            source=self.owner, target=None, target_companion=self.companion
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            CharacterRelationship.objects.create(source=self.owner, target_companion=self.companion)

    def test_sheet_pair_uniqueness_survives(self) -> None:
        other = CharacterSheetFactory()
        CharacterRelationshipFactory(source=self.owner, target=other)
        with self.assertRaises(IntegrityError), transaction.atomic():
            CharacterRelationship.objects.create(source=self.owner, target=other)

    def test_two_companions_two_rows(self) -> None:
        second = CompanionFactory(owner=self.owner, name="Ember")
        CharacterRelationshipFactory(
            source=self.owner, target=None, target_companion=self.companion
        )
        CharacterRelationshipFactory(source=self.owner, target=None, target_companion=second)
        self.assertEqual(CharacterRelationship.objects.filter(source=self.owner).count(), 2)
