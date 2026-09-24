"""Companion-targeted relationships (#3575): model constraints and services (#3957)."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from world.character_sheets.factories import CharacterSheetFactory
from world.companions.factories import CompanionFactory
from world.relationships.factories import RelationshipTypeFactory
from world.relationships.models import CharacterRelationship
from world.relationships.services import companion_target_error, declare_label, get_or_create_side


class CompanionTargetModelTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.owner = CharacterSheetFactory()
        cls.companion = CompanionFactory(owner=cls.owner, name="Ash")

    def test_companion_target_row_saves_and_names_the_companion(self) -> None:
        rel = get_or_create_side(source=self.owner, target_companion=self.companion)
        self.assertIsNone(rel.target)
        self.assertEqual(rel.target_companion, self.companion)
        self.assertEqual(rel.target_name, "Ash")
        self.assertIn("Ash", str(rel))

    def test_sheet_target_name_is_the_character_key(self) -> None:
        other = CharacterSheetFactory()
        rel = get_or_create_side(source=self.owner, target=other)
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
        get_or_create_side(source=self.owner, target_companion=self.companion)
        with self.assertRaises(IntegrityError), transaction.atomic():
            CharacterRelationship.objects.create(source=self.owner, target_companion=self.companion)

    def test_sheet_pair_uniqueness_survives(self) -> None:
        other = CharacterSheetFactory()
        get_or_create_side(source=self.owner, target=other)
        with self.assertRaises(IntegrityError), transaction.atomic():
            CharacterRelationship.objects.create(source=self.owner, target=other)

    def test_two_companions_two_rows(self) -> None:
        second = CompanionFactory(owner=self.owner, name="Ember")
        get_or_create_side(source=self.owner, target_companion=self.companion)
        get_or_create_side(source=self.owner, target_companion=second)
        self.assertEqual(CharacterRelationship.objects.filter(source=self.owner).count(), 2)


class CompanionTargetErrorTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.owner = CharacterSheetFactory()
        cls.companion = CompanionFactory(owner=cls.owner, name="Ash")

    def test_bonded_active_companion_has_no_error(self) -> None:
        self.assertEqual(companion_target_error(self.owner, self.companion), "")

    def test_non_owner_is_refused(self) -> None:
        stranger = CharacterSheetFactory()
        self.assertEqual(
            companion_target_error(stranger, self.companion), "That companion is not bonded to you."
        )

    def test_released_companion_is_refused(self) -> None:
        released = CompanionFactory(owner=self.owner, released_at=timezone.now())
        self.assertEqual(
            companion_target_error(self.owner, released), "That companion has been released."
        )


class CompanionSideServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.owner = CharacterSheetFactory()
        cls.companion = CompanionFactory(owner=cls.owner, name="Ash")
        cls.bonded = RelationshipTypeFactory(name="Bonded")

    def test_get_or_create_side_targets_companion_and_labels_can_be_declared(self) -> None:
        side = get_or_create_side(source=self.owner, target_companion=self.companion)
        self.assertIsNone(side.target)
        self.assertEqual(side.target_companion, self.companion)
        self.assertTrue(side.is_active)
        label = declare_label(side=side, type=self.bonded)
        self.assertEqual(label.relationship_id, side.pk)

    def test_exactly_one_target_required(self) -> None:
        other = CharacterSheetFactory()
        with self.assertRaises(ValueError):
            get_or_create_side(source=self.owner, target=other, target_companion=self.companion)
        with self.assertRaises(ValueError):
            get_or_create_side(source=self.owner)
