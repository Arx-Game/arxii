"""Tests for heredity stubs and the Parent Dominance service (#2815)."""

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.forms.factories import FormTraitFactory, FormTraitOptionFactory
from world.roster.constants import ParentageKind, PowerBand
from world.roster.factories import (
    KinspersonFactory,
    KinspersonTraitValueFactory,
    ParentageEdgeFactory,
)
from world.roster.models import KinspersonTraitValue


class KinspersonHeredityFieldsTest(TestCase):
    """New stub fields default to unspecified."""

    def test_species_and_band_default_null(self):
        kin = KinspersonFactory()
        self.assertIsNone(kin.species)
        self.assertIsNone(kin.power_band)

    def test_band_assignable(self):
        kin = KinspersonFactory(power_band=PowerBand.GRAND)
        self.assertEqual(kin.power_band, PowerBand.GRAND)


class KinspersonTraitValueTest(TestCase):
    """Pinned values are unique per (kinsperson, trait)."""

    @classmethod
    def setUpTestData(cls):
        cls.kin = KinspersonFactory()
        cls.trait = FormTraitFactory(name="hair_color")
        cls.red = FormTraitOptionFactory(trait=cls.trait, name="red")
        cls.black = FormTraitOptionFactory(trait=cls.trait, name="black")

    def test_pin_unique_per_trait(self):
        KinspersonTraitValueFactory(kinsperson=self.kin, trait=self.trait, option=self.red)
        with transaction.atomic(), self.assertRaises(IntegrityError):
            KinspersonTraitValue.objects.create(
                kinsperson=self.kin, trait=self.trait, option=self.black
            )

    def test_pin_get_or_create_does_not_clobber(self):
        KinspersonTraitValueFactory(kinsperson=self.kin, trait=self.trait, option=self.red)
        pin, created = KinspersonTraitValue.objects.get_or_create(
            kinsperson=self.kin, trait=self.trait, defaults={"option": self.black}
        )
        self.assertFalse(created)
        self.assertEqual(pin.option, self.red)


class RitualInvokerConstraintTest(TestCase):
    """At most one ritual invoker per child."""

    def test_second_invoker_rejected(self):
        child = KinspersonFactory()
        ParentageEdgeFactory(
            child=child,
            kind=ParentageKind.TREE_OF_SOULS,
            is_ritual_invoker=True,
        )
        with transaction.atomic(), self.assertRaises(IntegrityError):
            ParentageEdgeFactory(
                child=child,
                kind=ParentageKind.TREE_OF_SOULS,
                is_ritual_invoker=True,
            )

    def test_multiple_non_invoker_edges_allowed(self):
        child = KinspersonFactory()
        ParentageEdgeFactory(child=child, kind=ParentageKind.TREE_OF_SOULS)
        ParentageEdgeFactory(child=child, kind=ParentageKind.TREE_OF_SOULS)
        self.assertEqual(child.parentage_up.count(), 2)
