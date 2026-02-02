"""Tests for Motif, MotifResonance, and MotifResonanceAssociation models."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import (
    MotifFactory,
    MotifResonanceAssociationFactory,
    MotifResonanceFactory,
    ResonanceAssociationFactory,
    ResonanceModifierTypeFactory,
)
from world.magic.models import (
    Motif,
    MotifResonance,
    MotifResonanceAssociation,
)


class MotifModelTests(TestCase):
    """Tests for the Motif model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all test methods."""
        cls.character_sheet = CharacterSheetFactory()

    def test_motif_creation_with_character(self):
        """Test creating a Motif with a character."""
        motif = Motif.objects.create(
            character=self.character_sheet,
            description="A swirling darkness infused with spider silk.",
        )
        self.assertEqual(motif.character, self.character_sheet)
        self.assertEqual(motif.description, "A swirling darkness infused with spider silk.")
        self.assertIn("Motif of", str(motif))

    def test_motif_requires_character(self):
        """Test that Motif requires a character."""
        # Creating a motif without a character should violate NOT NULL constraint
        with self.assertRaises(IntegrityError):
            Motif.objects.create(
                character=None,
                description="An orphan motif.",
            )

    def test_motif_one_to_one_with_character(self):
        """Test OneToOne relationship prevents duplicate motifs per character."""
        Motif.objects.create(
            character=self.character_sheet,
            description="First motif.",
        )
        with self.assertRaises(IntegrityError):
            Motif.objects.create(
                character=self.character_sheet,
                description="Second motif - should fail.",
            )


class MotifResonanceModelTests(TestCase):
    """Tests for the MotifResonance model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all test methods."""
        cls.character_sheet = CharacterSheetFactory()
        cls.motif = Motif.objects.create(
            character=cls.character_sheet,
            description="A test motif.",
        )
        cls.resonance = ResonanceModifierTypeFactory()

    def test_motif_resonance_creation(self):
        """Test creating a MotifResonance."""
        motif_resonance = MotifResonance.objects.create(
            motif=self.motif,
            resonance=self.resonance,
            is_from_gift=True,
        )
        self.assertEqual(motif_resonance.motif, self.motif)
        self.assertEqual(motif_resonance.resonance, self.resonance)
        self.assertTrue(motif_resonance.is_from_gift)
        self.assertIn("(from gift)", str(motif_resonance))

    def test_motif_resonance_optional(self):
        """Test creating an optional MotifResonance (not from gift)."""
        motif_resonance = MotifResonance.objects.create(
            motif=self.motif,
            resonance=self.resonance,
            is_from_gift=False,
        )
        self.assertFalse(motif_resonance.is_from_gift)
        self.assertIn("(optional)", str(motif_resonance))

    def test_motif_resonance_unique_together(self):
        """Test unique_together constraint on motif + resonance."""
        MotifResonance.objects.create(
            motif=self.motif,
            resonance=self.resonance,
            is_from_gift=True,
        )
        with self.assertRaises(IntegrityError):
            MotifResonance.objects.create(
                motif=self.motif,
                resonance=self.resonance,
                is_from_gift=False,
            )


class MotifResonanceAssociationModelTests(TestCase):
    """Tests for the MotifResonanceAssociation model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all test methods."""
        cls.character_sheet = CharacterSheetFactory()
        cls.motif = Motif.objects.create(
            character=cls.character_sheet,
            description="A test motif.",
        )
        cls.resonance = ResonanceModifierTypeFactory()
        cls.motif_resonance = MotifResonance.objects.create(
            motif=cls.motif,
            resonance=cls.resonance,
            is_from_gift=True,
        )
        cls.association = ResonanceAssociationFactory(name="Spiders")

    def test_motif_resonance_association_creation(self):
        """Test creating a MotifResonanceAssociation."""
        mra = MotifResonanceAssociation.objects.create(
            motif_resonance=self.motif_resonance,
            association=self.association,
        )
        self.assertEqual(mra.motif_resonance, self.motif_resonance)
        self.assertEqual(mra.association, self.association)
        self.assertIn("Spiders", str(mra))

    def test_association_unique_together(self):
        """Test unique_together constraint on motif_resonance + association."""
        MotifResonanceAssociation.objects.create(
            motif_resonance=self.motif_resonance,
            association=self.association,
        )
        with self.assertRaises(IntegrityError):
            MotifResonanceAssociation.objects.create(
                motif_resonance=self.motif_resonance,
                association=self.association,
            )

    def test_associations_limit_max_five(self):
        """Test that maximum 5 associations per motif resonance is enforced."""
        # Create 5 associations (the maximum)
        for i in range(5):
            assoc = ResonanceAssociationFactory(name=f"Association {i}")
            MotifResonanceAssociation.objects.create(
                motif_resonance=self.motif_resonance,
                association=assoc,
            )

        # The 6th should raise ValidationError
        sixth_assoc = ResonanceAssociationFactory(name="Sixth Association")
        with self.assertRaises(ValidationError) as context:
            MotifResonanceAssociation.objects.create(
                motif_resonance=self.motif_resonance,
                association=sixth_assoc,
            )
        self.assertIn("Maximum 5 associations", str(context.exception))

    def test_associations_limit_allows_editing_existing(self):
        """Test that editing an existing association works even at max count."""
        # Create 5 associations
        associations = []
        for i in range(5):
            assoc = ResonanceAssociationFactory(name=f"Assoc {i}")
            mra = MotifResonanceAssociation.objects.create(
                motif_resonance=self.motif_resonance,
                association=assoc,
            )
            associations.append(mra)

        # Editing the first one should still work
        first_mra = associations[0]
        new_assoc = ResonanceAssociationFactory(name="New Association")

        # Delete the first, create with new association - should work
        first_mra.delete()
        MotifResonanceAssociation.objects.create(
            motif_resonance=self.motif_resonance,
            association=new_assoc,
        )
        self.assertEqual(self.motif_resonance.associations.count(), 5)


class MotifFactoryTests(TestCase):
    """Tests for the Motif factories."""

    def test_motif_factory_creates_valid_motif(self):
        """Test that MotifFactory creates a valid Motif."""
        motif = MotifFactory()
        self.assertIsInstance(motif, Motif)
        self.assertIsNotNone(motif.character)
        self.assertTrue(motif.description)

    def test_motif_resonance_factory_creates_valid_resonance(self):
        """Test that MotifResonanceFactory creates a valid MotifResonance."""
        motif_resonance = MotifResonanceFactory()
        self.assertIsInstance(motif_resonance, MotifResonance)
        self.assertIsNotNone(motif_resonance.motif)
        self.assertIsNotNone(motif_resonance.resonance)

    def test_motif_resonance_association_factory_creates_valid_association(self):
        """Test that MotifResonanceAssociationFactory creates valid association."""
        mra = MotifResonanceAssociationFactory()
        self.assertIsInstance(mra, MotifResonanceAssociation)
        self.assertIsNotNone(mra.motif_resonance)
        self.assertIsNotNone(mra.association)
