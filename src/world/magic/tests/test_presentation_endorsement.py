"""Tests for PresentationEndorsement model (#514)."""

from django.db import IntegrityError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.items.factories import FashionPresentationFactory
from world.magic.models import PresentationEndorsement


class PresentationEndorsementModelTest(TestCase):
    """Tests for the PresentationEndorsement model.

    Verifies the unique constraint, reverse accessor names (from EndorsementBase),
    and the FK to FashionPresentation.
    """

    @classmethod
    def setUpTestData(cls):
        cls.endorser = CharacterSheetFactory()
        cls.endorsee = CharacterSheetFactory()
        cls.presentation = FashionPresentationFactory()

    def test_create_endorsement(self):
        """Can create a PresentationEndorsement with required fields."""
        endorsement = PresentationEndorsement.objects.create(
            endorser_sheet=self.endorser,
            endorsee_sheet=self.endorsee,
            presentation=self.presentation,
        )
        self.assertEqual(endorsement.weight, 1)
        self.assertIsNone(endorsement.persona_snapshot_id)
        self.assertIsNotNone(endorsement.created_at)

    def test_str_representation(self):
        """__str__ shows endorser_sheet_id and presentation_id."""
        endorsement = PresentationEndorsement.objects.create(
            endorser_sheet=self.endorser,
            endorsee_sheet=self.endorsee,
            presentation=self.presentation,
        )
        expected = (
            f"PresentationEndorsement({self.endorser.pk}->{self.presentation.pk})"
        )
        self.assertEqual(str(endorsement), expected)

    def test_uniqueness_per_judge_and_presentation(self):
        """Duplicate (endorser_sheet, presentation) raises IntegrityError."""
        PresentationEndorsement.objects.create(
            endorser_sheet=self.endorser,
            endorsee_sheet=self.endorsee,
            presentation=self.presentation,
        )
        with self.assertRaises(IntegrityError):
            PresentationEndorsement.objects.create(
                endorser_sheet=self.endorser,
                endorsee_sheet=self.endorsee,
                presentation=self.presentation,
            )

    def test_reverse_accessor_given(self):
        """endorser_sheet.presentationendorsement_given returns the endorsement."""
        endorsement = PresentationEndorsement.objects.create(
            endorser_sheet=self.endorser,
            endorsee_sheet=self.endorsee,
            presentation=self.presentation,
        )
        result = list(self.endorser.presentationendorsement_given.all())
        self.assertIn(endorsement, result)

    def test_reverse_accessor_received(self):
        """endorsee_sheet.presentationendorsement_received returns the endorsement."""
        endorsement = PresentationEndorsement.objects.create(
            endorser_sheet=self.endorser,
            endorsee_sheet=self.endorsee,
            presentation=self.presentation,
        )
        result = list(self.endorsee.presentationendorsement_received.all())
        self.assertIn(endorsement, result)

    def test_presentation_endorsements_count(self):
        """presentation.endorsements.count() reflects created endorsements."""
        second_endorser = CharacterSheetFactory()
        PresentationEndorsement.objects.create(
            endorser_sheet=self.endorser,
            endorsee_sheet=self.endorsee,
            presentation=self.presentation,
        )
        PresentationEndorsement.objects.create(
            endorser_sheet=second_endorser,
            endorsee_sheet=self.endorsee,
            presentation=self.presentation,
        )
        self.assertEqual(self.presentation.endorsements.count(), 2)

    def test_different_endorser_same_presentation_allowed(self):
        """Two different endorsers can endorse the same presentation."""
        second_endorser = CharacterSheetFactory()
        e1 = PresentationEndorsement.objects.create(
            endorser_sheet=self.endorser,
            endorsee_sheet=self.endorsee,
            presentation=self.presentation,
        )
        e2 = PresentationEndorsement.objects.create(
            endorser_sheet=second_endorser,
            endorsee_sheet=self.endorsee,
            presentation=self.presentation,
        )
        self.assertNotEqual(e1.pk, e2.pk)

    def test_custom_weight(self):
        """weight field can be set to a custom value."""
        endorsement = PresentationEndorsement.objects.create(
            endorser_sheet=self.endorser,
            endorsee_sheet=self.endorsee,
            presentation=self.presentation,
            weight=3,
        )
        self.assertEqual(endorsement.weight, 3)
