"""Tests for heredity stubs and the Parent Dominance service (#2815)."""

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.character_sheets.factories import GenderFactory
from world.forms.factories import (
    FormTraitFactory,
    FormTraitOptionFactory,
    SpeciesFormTraitFactory,
)
from world.roster.constants import ParentageKind, PowerBand
from world.roster.factories import (
    KinspersonFactory,
    KinspersonTraitValueFactory,
    ParentageEdgeFactory,
)
from world.roster.models import KinspersonTraitValue
from world.roster.services.heredity import (
    ParentLine,
    base_trait_options,
    derivable_species,
    derive_lines_for_child,
    inherited_options,
)
from world.species.factories import SpeciesFactory


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


class DerivableSpeciesTest(TestCase):
    """Parent Dominance math: maternal default, flip on strictly-greater band."""

    @classmethod
    def setUpTestData(cls):
        cls.khati = SpeciesFactory(name="Khati")
        cls.human = SpeciesFactory(name="Human")

    @staticmethod
    def _lines(maternal_band, paternal_band, maternal_species, paternal_species):
        return [
            ParentLine(
                kinsperson=None,
                species=maternal_species,
                band=maternal_band,
                is_dominant_role=True,
            ),
            ParentLine(
                kinsperson=None,
                species=paternal_species,
                band=paternal_band,
                is_dominant_role=False,
            ),
        ]

    def test_equal_bands_maternal_only(self):
        result = derivable_species(
            self._lines(None, None, self.khati, self.human),
            fallback_maternal=self.khati,
        )
        self.assertEqual(result.allowed, [self.khati])
        self.assertFalse(result.chimeric_possible)

    def test_sub_puissant_bands_are_one_tier(self):
        result = derivable_species(
            self._lines(PowerBand.QUIESCENT, PowerBand.POTENTIAL, self.khati, self.human),
            fallback_maternal=self.khati,
        )
        self.assertEqual(result.allowed, [self.khati])

    def test_puissant_father_flips(self):
        result = derivable_species(
            self._lines(None, PowerBand.PUISSANT, self.khati, self.human),
            fallback_maternal=self.khati,
        )
        self.assertEqual(result.allowed, [self.khati, self.human])

    def test_stronger_mother_no_flip(self):
        result = derivable_species(
            self._lines(PowerBand.GRAND, PowerBand.PUISSANT, self.khati, self.human),
            fallback_maternal=self.khati,
        )
        self.assertEqual(result.allowed, [self.khati])

    def test_both_grand_chimeric_possible(self):
        result = derivable_species(
            self._lines(PowerBand.GRAND, PowerBand.TRANSCENDENT, self.khati, self.human),
            fallback_maternal=self.khati,
        )
        self.assertTrue(result.chimeric_possible)

    def test_both_grand_same_species_not_chimeric(self):
        result = derivable_species(
            self._lines(PowerBand.GRAND, PowerBand.GRAND, self.khati, self.khati),
            fallback_maternal=self.khati,
        )
        self.assertFalse(result.chimeric_possible)

    def test_undefined_mother_uses_fallback(self):
        lines = [
            ParentLine(kinsperson=None, species=None, band=None, is_dominant_role=True),
            ParentLine(kinsperson=None, species=self.human, band=None, is_dominant_role=False),
        ]
        result = derivable_species(lines, fallback_maternal=self.khati)
        self.assertEqual(result.allowed, [self.khati])


class DeriveLinesForChildTest(TestCase):
    """Role derivation is kind-aware: gender for BIOLOGICAL, invoker for Tree."""

    @classmethod
    def setUpTestData(cls):
        cls.female = GenderFactory(key="female", display_name="Female")
        cls.male = GenderFactory(key="male", display_name="Male")
        cls.khati = SpeciesFactory(name="Khati")
        cls.human = SpeciesFactory(name="Human")

    def test_biological_female_parent_is_dominant(self):
        child = KinspersonFactory()
        mother = KinspersonFactory(gender=self.female, species=self.khati)
        father = KinspersonFactory(gender=self.male, species=self.human)
        ParentageEdgeFactory(child=child, parent=mother)
        ParentageEdgeFactory(child=child, parent=father)
        lines = derive_lines_for_child(child)
        dominant = [line for line in lines if line.is_dominant_role]
        self.assertEqual(len(lines), 2)
        self.assertEqual(len(dominant), 1)
        self.assertEqual(dominant[0].kinsperson, mother)
        self.assertEqual(dominant[0].species, self.khati)

    def test_tree_invoker_is_dominant_regardless_of_gender(self):
        child = KinspersonFactory()
        invoker = KinspersonFactory(gender=self.male, species=self.khati)
        other = KinspersonFactory(gender=self.male, species=self.human)
        ParentageEdgeFactory(
            child=child,
            parent=invoker,
            kind=ParentageKind.TREE_OF_SOULS,
            is_ritual_invoker=True,
        )
        ParentageEdgeFactory(child=child, parent=other, kind=ParentageKind.TREE_OF_SOULS)
        lines = derive_lines_for_child(child)
        dominant = [line for line in lines if line.is_dominant_role]
        self.assertEqual(len(dominant), 1)
        self.assertEqual(dominant[0].kinsperson, invoker)


class InheritedOptionsTest(TestCase):
    """Cross-line options come from the parent's pins, else their palette,
    minus everything already in the child's own palette (overlap = no tell)."""

    @classmethod
    def setUpTestData(cls):
        cls.khati = SpeciesFactory(name="Khati")
        cls.human = SpeciesFactory(name="Human")
        cls.hair = FormTraitFactory(name="hair_color")
        cls.black = FormTraitOptionFactory(trait=cls.hair, name="black")
        cls.red = FormTraitOptionFactory(trait=cls.hair, name="red")
        cls.blonde = FormTraitOptionFactory(trait=cls.hair, name="blonde")
        khati_hair = SpeciesFormTraitFactory(species=cls.khati, trait=cls.hair)
        khati_hair.allowed_options.set([cls.black])
        human_hair = SpeciesFormTraitFactory(species=cls.human, trait=cls.hair)
        human_hair.allowed_options.set([cls.black, cls.red, cls.blonde])

    def test_unpinned_parent_exposes_palette_minus_overlap(self):
        father = KinspersonFactory(species=self.human, name="Bob")
        lines = [
            ParentLine(kinsperson=None, species=self.khati, band=None, is_dominant_role=True),
            ParentLine(kinsperson=father, species=self.human, band=None, is_dominant_role=False),
        ]
        inherited = inherited_options(self.khati, lines)
        self.assertEqual(len(inherited), 1)
        entry = inherited[0]
        self.assertEqual(entry.trait, self.hair)
        self.assertEqual(set(entry.options), {self.red, self.blonde})
        self.assertEqual(entry.source, "Bob")

    def test_pinned_parent_exposes_only_the_pin(self):
        father = KinspersonFactory(species=self.human, name="Bob")
        KinspersonTraitValueFactory(kinsperson=father, trait=self.hair, option=self.red)
        lines = [
            ParentLine(kinsperson=None, species=self.khati, band=None, is_dominant_role=True),
            ParentLine(kinsperson=father, species=self.human, band=None, is_dominant_role=False),
        ]
        inherited = inherited_options(self.khati, lines)
        self.assertEqual(len(inherited), 1)
        self.assertEqual(inherited[0].options, [self.red])

    def test_pinned_overlap_yields_no_tell(self):
        father = KinspersonFactory(species=self.human, name="Bob")
        KinspersonTraitValueFactory(kinsperson=father, trait=self.hair, option=self.black)
        lines = [
            ParentLine(kinsperson=None, species=self.khati, band=None, is_dominant_role=True),
            ParentLine(kinsperson=father, species=self.human, band=None, is_dominant_role=False),
        ]
        inherited = inherited_options(self.khati, lines)
        self.assertEqual(inherited, [])

    def test_same_species_parent_contributes_nothing(self):
        mother = KinspersonFactory(species=self.khati)
        lines = [
            ParentLine(kinsperson=mother, species=self.khati, band=None, is_dominant_role=True),
        ]
        self.assertEqual(inherited_options(self.khati, lines), [])

    def test_unpersisted_parent_species_only(self):
        lines = [
            ParentLine(kinsperson=None, species=self.khati, band=None, is_dominant_role=True),
            ParentLine(kinsperson=None, species=self.human, band=None, is_dominant_role=False),
        ]
        inherited = inherited_options(self.khati, lines)
        self.assertEqual(len(inherited), 1)
        self.assertEqual(set(inherited[0].options), {self.red, self.blonde})
        self.assertEqual(inherited[0].source, "Human parent")


class BaseTraitOptionsTest(TestCase):
    """Defined-parents narrowing: children work from the family look (#2815).

    Narrowing triggers only when EVERY parent line is pinned for a trait; an
    unpinned side (or a single recorded parent) keeps the palette open.
    """

    @classmethod
    def setUpTestData(cls):
        cls.khati = SpeciesFactory(name="Khati")
        cls.human = SpeciesFactory(name="Human")
        cls.hair = FormTraitFactory(name="hair_color")
        cls.black = FormTraitOptionFactory(trait=cls.hair, name="black")
        cls.brown = FormTraitOptionFactory(trait=cls.hair, name="brown")
        cls.white = FormTraitOptionFactory(trait=cls.hair, name="white")
        cls.red = FormTraitOptionFactory(trait=cls.hair, name="red")
        khati_hair = SpeciesFormTraitFactory(species=cls.khati, trait=cls.hair)
        khati_hair.allowed_options.set([cls.black, cls.brown, cls.white])
        human_hair = SpeciesFormTraitFactory(species=cls.human, trait=cls.hair)
        human_hair.allowed_options.set([cls.black, cls.brown, cls.red])

    def _lines(self, mother, father):
        return [
            ParentLine(
                kinsperson=mother,
                species=mother.species if mother else None,
                band=None,
                is_dominant_role=True,
            ),
            ParentLine(
                kinsperson=father,
                species=father.species if father else None,
                band=None,
                is_dominant_role=False,
            ),
        ]

    def test_both_parents_pinned_narrows_mother_first(self):
        mother = KinspersonFactory(species=self.khati)
        father = KinspersonFactory(species=self.khati)
        KinspersonTraitValueFactory(kinsperson=mother, trait=self.hair, option=self.brown)
        KinspersonTraitValueFactory(kinsperson=father, trait=self.hair, option=self.black)
        base = base_trait_options(self.khati, self._lines(mother, father))
        self.assertEqual(base[self.hair], [self.brown, self.black])

    def test_unpinned_side_keeps_palette_open(self):
        mother = KinspersonFactory(species=self.khati)
        father = KinspersonFactory(species=self.khati)
        KinspersonTraitValueFactory(kinsperson=mother, trait=self.hair, option=self.brown)
        base = base_trait_options(self.khati, self._lines(mother, father))
        self.assertEqual(set(base[self.hair]), {self.black, self.brown, self.white})

    def test_single_line_keeps_palette(self):
        mother = KinspersonFactory(species=self.khati)
        KinspersonTraitValueFactory(kinsperson=mother, trait=self.hair, option=self.brown)
        lines = self._lines(mother, None)[:1]
        base = base_trait_options(self.khati, lines)
        self.assertEqual(set(base[self.hair]), {self.black, self.brown, self.white})

    def test_cross_species_pin_triggers_narrowing_but_rides_inherited(self):
        # Mother khati pinned brown; father human pinned red (off khati palette).
        # Base narrows to the mother's value only; red stays in the father's
        # labeled inherited group — no duplicate between the two surfaces.
        mother = KinspersonFactory(species=self.khati)
        father = KinspersonFactory(species=self.human, name="Bob")
        KinspersonTraitValueFactory(kinsperson=mother, trait=self.hair, option=self.brown)
        KinspersonTraitValueFactory(kinsperson=father, trait=self.hair, option=self.red)
        lines = self._lines(mother, father)
        base = base_trait_options(self.khati, lines)
        self.assertEqual(base[self.hair], [self.brown])
        inherited = inherited_options(self.khati, lines)
        self.assertEqual(len(inherited), 1)
        self.assertEqual(inherited[0].options, [self.red])

    def test_undefined_parents_keep_palette(self):
        lines = [
            ParentLine(kinsperson=None, species=self.khati, band=None, is_dominant_role=True),
            ParentLine(kinsperson=None, species=self.human, band=None, is_dominant_role=False),
        ]
        base = base_trait_options(self.khati, lines)
        self.assertEqual(set(base[self.hair]), {self.black, self.brown, self.white})
