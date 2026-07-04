"""
Tests for core.natural_keys module.

Tests the NaturalKeyMixin and NaturalKeyManager that provide DRY natural key
support for Django model serialization.

Uses existing models from the codebase to avoid needing test-only migrations.
"""

from django.test import TestCase

from core.natural_keys import (
    NaturalKeyConfigError,
    NaturalKeyMixin,
    count_natural_key_args,
)
from world.forms.models import SpeciesFormTrait
from world.species.models import Species, SpeciesStatBonus
from world.traits.models import Trait, TraitCategory, TraitRankDescription, TraitType


class NaturalKeyMixinTests(TestCase):
    """Test the NaturalKeyMixin.natural_key() method."""

    def test_simple_natural_key(self):
        """Test natural key with single field."""
        trait = Trait.objects.create(
            name="test_strength",
            trait_type=TraitType.STAT,
            category=TraitCategory.PHYSICAL,
        )

        key = trait.natural_key()
        self.assertEqual(key, ("test_strength",))

    def test_natural_key_with_fk(self):
        """Test natural key that includes a foreign key."""
        trait = Trait.objects.create(
            name="test_agility",
            trait_type=TraitType.STAT,
            category=TraitCategory.PHYSICAL,
        )
        rank_desc = TraitRankDescription.objects.create(
            trait=trait,
            value=30,
            label="Good",
            description="Above average",
        )

        # Natural key should flatten the FK's natural key
        key = rank_desc.natural_key()
        self.assertEqual(key, ("test_agility", 30))

    def test_fk_with_char_field_natural_key(self):
        """Test natural key with FK and CharField."""
        species = Species.objects.create(name="TestElf", description="Test species")
        bonus = SpeciesStatBonus.objects.create(
            species=species,
            stat="strength",  # CharField with PrimaryStat choices
            value=1,
        )

        # SpeciesStatBonus key: (species, stat)
        # species key: (name,) -> (species_name,)
        # stat is a CharField, not FK
        key = bonus.natural_key()
        self.assertEqual(key, ("TestElf", "strength"))

    def test_missing_config_raises_error(self):
        """Test that model without NaturalKeyConfig raises error."""

        class NoConfigModel(NaturalKeyMixin):
            pass

        obj = NoConfigModel()
        with self.assertRaises(NaturalKeyConfigError) as cm:
            obj.natural_key()
        self.assertIn("missing NaturalKeyConfig", str(cm.exception))


class NaturalKeyManagerTests(TestCase):
    """Test the NaturalKeyManager.get_by_natural_key() method."""

    def setUp(self):
        """Create test objects in the database."""
        # Simple model
        self.trait = Trait.objects.create(
            name="nk_test_trait",
            trait_type=TraitType.STAT,
            category=TraitCategory.PHYSICAL,
        )

        # Model with FK
        self.rank_desc = TraitRankDescription.objects.create(
            trait=self.trait,
            value=50,
            label="Excellent",
            description="Very high",
        )

        # FK with CharField model
        self.species = Species.objects.create(name="NKTestSpecies", description="Test")
        self.stat_bonus = SpeciesStatBonus.objects.create(
            species=self.species,
            stat="agility",
            value=1,
        )

    def test_simple_get_by_natural_key(self):
        """Test lookup with single-field natural key."""
        found = Trait.objects.get_by_natural_key("nk_test_trait")
        self.assertEqual(found.pk, self.trait.pk)

    def test_get_by_natural_key_with_fk(self):
        """Test lookup with FK in natural key."""
        # Natural key is (trait_name, value)
        found = TraitRankDescription.objects.get_by_natural_key("nk_test_trait", 50)
        self.assertEqual(found.pk, self.rank_desc.pk)

    def test_fk_with_char_field_get_by_natural_key(self):
        """Test lookup with FK and CharField in natural key."""
        # Natural key is (species_name, stat)
        found = SpeciesStatBonus.objects.get_by_natural_key("NKTestSpecies", "agility")
        self.assertEqual(found.pk, self.stat_bonus.pk)

    def test_not_found_raises_does_not_exist(self):
        """Test that non-existent natural key raises DoesNotExist."""
        with self.assertRaises(Trait.DoesNotExist):
            Trait.objects.get_by_natural_key("nonexistent_trait_xyz")

    def test_fk_not_found_raises_does_not_exist(self):
        """Test that non-existent FK in natural key raises DoesNotExist."""
        with self.assertRaises(Trait.DoesNotExist):
            TraitRankDescription.objects.get_by_natural_key("nonexistent_trait", 50)

    def test_too_few_args_raises_error(self):
        """Test that too few natural key values raises error."""
        with self.assertRaises(NaturalKeyConfigError) as cm:
            # TraitRankDescription needs (trait_name, value), only giving trait_name
            TraitRankDescription.objects.get_by_natural_key("nk_test_trait")
        self.assertIn("Not enough", str(cm.exception))

    def test_too_many_args_raises_error(self):
        """Test that too many natural key values raises error."""
        with self.assertRaises(NaturalKeyConfigError) as cm:
            Trait.objects.get_by_natural_key("nk_test_trait", "extra_arg")
        self.assertIn("Too many", str(cm.exception))


class CountNaturalKeyArgsTests(TestCase):
    """Test the count_natural_key_args helper function."""

    def test_simple_model_count(self):
        """Test count for model with single field."""
        count = count_natural_key_args(Trait)
        self.assertEqual(count, 1)

    def test_fk_model_count(self):
        """Test count for model with FK (consumes FK's args too)."""
        # TraitRankDescription: trait (1 arg from Trait) + value (1 arg) = 2
        count = count_natural_key_args(TraitRankDescription)
        self.assertEqual(count, 2)

    def test_fk_with_char_field_count(self):
        """Test count for model with FK and CharField."""
        # SpeciesStatBonus: species (1) + stat (1) = 2
        self.assertEqual(count_natural_key_args(SpeciesStatBonus), 2)


class NaturalKeyDependenciesTests(TestCase):
    """Test the natural_key_dependencies class method."""

    def test_no_dependencies(self):
        """Test model with no dependencies."""
        deps = Trait.natural_key_dependencies()
        self.assertEqual(deps, [])

    def test_single_dependency(self):
        """Test model with single dependency."""
        deps = TraitRankDescription.natural_key_dependencies()
        self.assertEqual(deps, ["traits.Trait"])

    def test_multiple_dependencies(self):
        """Test model with multiple dependencies."""
        deps = SpeciesFormTrait.natural_key_dependencies()
        self.assertIn("species.Species", deps)
        self.assertIn("forms.FormTrait", deps)


class RoundTripTests(TestCase):
    """Test that natural_key() and get_by_natural_key() are inverses."""

    def test_round_trip_simple(self):
        """Test round-trip for simple model."""
        trait = Trait.objects.create(
            name="roundtrip_test",
            trait_type=TraitType.SKILL,
            category=TraitCategory.OTHER,
        )

        key = trait.natural_key()
        found = Trait.objects.get_by_natural_key(*key)
        self.assertEqual(found.pk, trait.pk)

    def test_round_trip_with_fk(self):
        """Test round-trip for model with FK."""
        trait = Trait.objects.create(
            name="roundtrip_fk_test",
            trait_type=TraitType.STAT,
            category=TraitCategory.MENTAL,
        )
        rank_desc = TraitRankDescription.objects.create(
            trait=trait,
            value=40,
            label="Good",
            description="Above average ability",
        )

        key = rank_desc.natural_key()
        found = TraitRankDescription.objects.get_by_natural_key(*key)
        self.assertEqual(found.pk, rank_desc.pk)

    def test_round_trip_fk_with_char_field(self):
        """Test round-trip for model with FK and CharField."""
        species = Species.objects.create(name="RoundTripSpecies", description="Test")
        bonus = SpeciesStatBonus.objects.create(
            species=species,
            stat="charm",
            value=-1,
        )

        key = bonus.natural_key()
        # Key should be (species_name, stat)
        self.assertEqual(key, ("RoundTripSpecies", "charm"))

        found = SpeciesStatBonus.objects.get_by_natural_key(*key)
        self.assertEqual(found.pk, bonus.pk)
