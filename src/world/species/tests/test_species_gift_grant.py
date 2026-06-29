"""Tests for SpeciesGiftGrant through-model (#1580)."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from world.conditions.factories import ConditionTemplateFactory
from world.magic.constants import GiftKind
from world.magic.factories import GiftFactory
from world.species.factories import SpeciesFactory, SpeciesGiftGrantFactory
from world.species.models import SpeciesGiftGrant


class SpeciesGiftGrantModelTests(TestCase):
    """Tests for the SpeciesGiftGrant through-model."""

    @classmethod
    def setUpTestData(cls):
        cls.species = SpeciesFactory(name="TestVampire")
        cls.minor_gift = GiftFactory(name="Nocturnal Sight", kind=GiftKind.MINOR)
        cls.major_gift = GiftFactory(name="Shadow Majesty", kind=GiftKind.MAJOR)
        cls.drawback = ConditionTemplateFactory(name="Sunlight Vulnerability")

    def test_grant_rejects_major_gift(self):
        """A grant whose gift.kind == MAJOR should raise ValidationError on full_clean()."""
        grant = SpeciesGiftGrant(species=self.species, gift=self.major_gift)
        with self.assertRaises(ValidationError) as ctx:
            grant.full_clean()
        self.assertIn("gift", ctx.exception.message_dict)

    def test_grant_accepts_minor_gift(self):
        """A MINOR gift should pass full_clean() without raising."""
        grant = SpeciesGiftGrant(species=self.species, gift=self.minor_gift)
        grant.full_clean()  # Should not raise

    def test_unique_per_species_gift(self):
        """A second grant with the same (species, gift) should raise IntegrityError."""
        SpeciesGiftGrant.objects.create(species=self.species, gift=self.minor_gift)
        with self.assertRaises(IntegrityError):
            SpeciesGiftGrant.objects.create(species=self.species, gift=self.minor_gift)

    def test_natural_key_roundtrip(self):
        """get_by_natural_key(species.name, gift.name) should return the row."""
        grant = SpeciesGiftGrant.objects.create(species=self.species, gift=self.minor_gift)
        fetched = SpeciesGiftGrant.objects.get_by_natural_key(
            self.species.name, self.minor_gift.name
        )
        self.assertEqual(fetched.pk, grant.pk)

    def test_grant_with_drawback(self):
        """A grant with a drawback_condition should save and display correctly."""
        grant = SpeciesGiftGrantFactory(
            species=self.species, gift=self.minor_gift, drawback_condition=self.drawback
        )
        self.assertEqual(grant.drawback_condition, self.drawback)
        self.assertIn("→", str(grant))

    def test_str_representation(self):
        """__str__ should include species name and gift name."""
        grant = SpeciesGiftGrantFactory(species=self.species, gift=self.minor_gift)
        result = str(grant)
        self.assertIn(self.species.name, result)
        self.assertIn(self.minor_gift.name, result)
