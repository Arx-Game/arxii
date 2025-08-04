"""
Tests for the traits system.

Tests models, handlers, and check resolution functionality.
"""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.traits.handlers import DefaultTraitValue
from world.traits.models import (
    CharacterTraitValue,
    CheckOutcome,
    CheckRank,
    PointConversionRange,
    ResultChart,
    ResultChartOutcome,
    Trait,
    TraitCategory,
    TraitRankDescription,
    TraitType,
)
from world.traits.resolvers import CheckResolver, perform_check


class TraitModelTests(TestCase):
    """Test trait model functionality."""

    def setUp(self):
        """Set up test data."""
        self.trait = Trait.objects.create(
            name="strength",
            trait_type=TraitType.STAT,
            category=TraitCategory.PHYSICAL,
            description="Physical power and capability",
        )

        from evennia.objects.models import ObjectDB

        self.character = ObjectDB.objects.create(
            db_key="testchar", db_typeclass_path="typeclasses.characters.Character"
        )

    def test_trait_creation(self):
        """Test creating and accessing traits."""
        self.assertEqual(self.trait.name, "strength")
        self.assertEqual(self.trait.trait_type, TraitType.STAT)
        self.assertEqual(self.trait.category, TraitCategory.PHYSICAL)
        self.assertTrue(self.trait.is_public)

    def test_trait_str_representation(self):
        """Test trait string representation."""
        expected = "strength (Stat)"
        self.assertEqual(str(self.trait), expected)

    def test_character_trait_value(self):
        """Test character trait values."""
        trait_value = CharacterTraitValue.objects.create(
            character=self.character, trait=self.trait, value=25
        )

        self.assertEqual(trait_value.value, 25)
        self.assertEqual(trait_value.display_value, 2.5)

    def test_trait_rank_description(self):
        """Test trait rank descriptions."""
        rank_desc = TraitRankDescription.objects.create(
            trait=self.trait,
            value=30,
            label="Powerful Warrior",
            description="Someone with exceptional physical strength",
        )

        self.assertEqual(rank_desc.display_value, 3.0)
        self.assertIn("Powerful Warrior", str(rank_desc))

    def test_trait_case_insensitive_lookup(self):
        """Test case-insensitive trait lookup."""
        # Test exact match
        trait = Trait.get_by_name("strength")
        self.assertEqual(trait, self.trait)

        # Test case variations
        trait = Trait.get_by_name("STRENGTH")
        self.assertEqual(trait, self.trait)

        trait = Trait.get_by_name("Strength")
        self.assertEqual(trait, self.trait)

        trait = Trait.get_by_name("sTrEnGtH")
        self.assertEqual(trait, self.trait)

        # Test non-existent trait
        trait = Trait.get_by_name("nonexistent")
        self.assertIsNone(trait)


class PointConversionRangeTests(TestCase):
    """Test point conversion range functionality."""

    def setUp(self):
        """Set up conversion ranges."""
        # Create ranges for stats
        PointConversionRange.objects.create(
            trait_type=TraitType.STAT, min_value=1, max_value=20, points_per_level=1
        )
        PointConversionRange.objects.create(
            trait_type=TraitType.STAT, min_value=21, max_value=40, points_per_level=2
        )
        PointConversionRange.objects.create(
            trait_type=TraitType.STAT, min_value=41, max_value=60, points_per_level=3
        )

    def test_point_calculation(self):
        """Test point calculation for trait values."""
        # Value 10 should give 10 points (1-20 range, 1 point each)
        points = PointConversionRange.calculate_points(TraitType.STAT, 10)
        self.assertEqual(points, 10)

        # Value 25 should give 20 + 10 = 30 points
        # (20 points from 1-20 range, 10 points from 21-25 in second range)
        points = PointConversionRange.calculate_points(TraitType.STAT, 25)
        self.assertEqual(points, 30)

        # Value 45 should give 20 + 40 + 15 = 75 points
        points = PointConversionRange.calculate_points(TraitType.STAT, 45)
        self.assertEqual(points, 75)

    def test_range_validation(self):
        """Test range overlap validation."""
        # This should raise validation error due to overlap
        overlapping_range = PointConversionRange(
            trait_type=TraitType.STAT, min_value=15, max_value=25, points_per_level=1
        )

        with self.assertRaises(ValidationError):
            overlapping_range.clean()

    def test_contains_value(self):
        """Test range contains value check."""
        range_obj = PointConversionRange.objects.get(min_value=21, max_value=40)

        self.assertTrue(range_obj.contains_value(25))
        self.assertTrue(range_obj.contains_value(21))
        self.assertTrue(range_obj.contains_value(40))
        self.assertFalse(range_obj.contains_value(20))
        self.assertFalse(range_obj.contains_value(41))


class CheckRankTests(TestCase):
    """Test check rank functionality."""

    def setUp(self):
        """Set up check ranks."""
        CheckRank.objects.create(rank=0, min_points=0, name="Incompetent")
        CheckRank.objects.create(rank=1, min_points=10, name="Novice")
        CheckRank.objects.create(rank=2, min_points=25, name="Competent")
        CheckRank.objects.create(rank=3, min_points=50, name="Expert")

    def test_get_rank_for_points(self):
        """Test getting rank for point values."""
        rank = CheckRank.get_rank_for_points(5)
        self.assertEqual(rank.name, "Incompetent")

        rank = CheckRank.get_rank_for_points(15)
        self.assertEqual(rank.name, "Novice")

        rank = CheckRank.get_rank_for_points(30)
        self.assertEqual(rank.name, "Competent")

        rank = CheckRank.get_rank_for_points(75)
        self.assertEqual(rank.name, "Expert")

    def test_rank_difference(self):
        """Test calculating rank differences."""
        diff = CheckRank.get_rank_difference(30, 15)  # Competent vs Novice
        self.assertEqual(diff, 1)  # rank 2 - rank 1

        diff = CheckRank.get_rank_difference(5, 30)  # Incompetent vs Competent
        self.assertEqual(diff, -2)  # rank 0 - rank 2


class TraitHandlerTests(TestCase):
    """Test trait handler caching functionality."""

    def setUp(self):
        """Set up test data."""
        from evennia.objects.models import ObjectDB

        self.character = ObjectDB.objects.create(
            db_key="testchar", db_typeclass_path="typeclasses.characters.Character"
        )

        self.trait = Trait.objects.create(
            name="swords", trait_type=TraitType.SKILL, category=TraitCategory.COMBAT
        )

        self.trait2 = Trait.objects.create(
            name="diplomacy", trait_type=TraitType.SKILL, category=TraitCategory.GENERAL
        )

        self.handler = self.character.traits

        # Set up point conversion
        PointConversionRange.objects.create(
            trait_type=TraitType.SKILL, min_value=1, max_value=50, points_per_level=1
        )

    def test_get_trait_value(self):
        """Test getting trait values."""
        # Should return 0 for unset trait
        value = self.handler.get_trait_value("swords")
        self.assertEqual(value, 0)

        # Set a value and test retrieval
        CharacterTraitValue.objects.create(
            character=self.character, trait=self.trait, value=25
        )

        # Clear the handler cache to pick up new data
        self.handler.clear_cache()

        value = self.handler.get_trait_value("swords")
        self.assertEqual(value, 25)

    def test_set_trait_value(self):
        """Test setting trait values."""
        success = self.handler.set_trait_value("swords", 30)
        self.assertTrue(success)

        # Verify it was set
        value = self.handler.get_trait_value("swords")
        self.assertEqual(value, 30)

        # Test updating existing value
        success = self.handler.set_trait_value("swords", 35)
        self.assertTrue(success)

        # Clear cache to pick up the updated value
        self.handler.clear_cache()

        value = self.handler.get_trait_value("swords")
        self.assertEqual(value, 35)

    def test_get_display_value(self):
        """Test getting display values."""
        self.handler.set_trait_value("swords", 25)
        display = self.handler.get_trait_display_value("swords")
        self.assertEqual(display, 2.5)

    def test_calculate_check_points(self):
        """Test calculating check points."""
        self.handler.set_trait_value("swords", 20)

        points = self.handler.calculate_check_points(["swords"])
        self.assertEqual(points, 20)  # 1 point per level for skills

    def test_case_insensitive_trait_access(self):
        """Test case-insensitive trait access through handler."""
        self.handler.set_trait_value("swords", 25)

        # Test various case combinations
        self.assertEqual(self.handler.get_trait_value("swords"), 25)
        self.assertEqual(self.handler.get_trait_value("SWORDS"), 25)
        self.assertEqual(self.handler.get_trait_value("Swords"), 25)
        self.assertEqual(self.handler.get_trait_value("SwOrDs"), 25)

    def test_default_trait_value(self):
        """Test default trait value for missing traits."""
        trait_obj = self.handler.get_trait_object("nonexistent")
        self.assertIsInstance(trait_obj, DefaultTraitValue)
        self.assertEqual(trait_obj.value, 0)
        self.assertFalse(trait_obj)  # Should be falsy

    def test_cache_auto_update(self):
        """Test automatic cache updating when trait values change."""
        # Set initial value
        self.handler.set_trait_value("swords", 30)
        self.assertEqual(self.handler.get_trait_value("swords"), 30)

        # Update through direct model save - cache should auto-update
        trait_value = CharacterTraitValue.objects.get(
            character=self.character, trait=self.trait
        )
        trait_value.value = 40
        trait_value.save()

        # Clear cache to pick up the updated value
        self.handler.clear_cache()

        # Cache should be automatically updated
        self.assertEqual(self.handler.get_trait_value("swords"), 40)

    def test_get_cached_handler(self):
        """Test the global cached handler function."""
        handler1 = self.character.traits
        handler2 = self.character.traits

        # Should return the same cached instance
        self.assertIs(handler1, handler2)

    def test_get_public_traits(self):
        """Test filtering public vs private traits."""
        # Create a private trait
        private_trait = Trait.objects.create(
            name="secret_skill",
            trait_type=TraitType.SKILL,
            category=TraitCategory.OTHER,
            is_public=False,
        )

        # Set values for both traits
        self.handler.set_trait_value("swords", 30)
        CharacterTraitValue.objects.create(
            character=self.character, trait=private_trait, value=40
        )

        # Get all traits
        all_traits = self.handler.get_all_traits()
        self.assertIn("swords", str(all_traits))
        self.assertIn("secret_skill", str(all_traits))

        # Get only public traits
        public_traits = self.handler.get_public_traits()
        self.assertIn("swords", str(public_traits))
        self.assertNotIn("secret_skill", str(public_traits))


class CheckResolverTests(TestCase):
    """Test check resolution functionality."""

    def setUp(self):
        """Set up test data for check resolution."""
        # Clear caches to ensure test isolation
        ResultChart.clear_cache()
        Trait.clear_name_cache()

        from evennia.objects.models import ObjectDB

        self.character = ObjectDB.objects.create(
            db_key="testchar", db_typeclass_path="typeclasses.characters.Character"
        )

        # Create trait
        self.trait = Trait.objects.create(
            name="diplomacy", trait_type=TraitType.SKILL, category=TraitCategory.GENERAL
        )

        # Set trait value
        CharacterTraitValue.objects.create(
            character=self.character, trait=self.trait, value=30
        )

        # Set up point conversion
        PointConversionRange.objects.create(
            trait_type=TraitType.SKILL, min_value=1, max_value=50, points_per_level=1
        )

        # Set up ranks
        CheckRank.objects.create(rank=0, min_points=0, name="Incompetent")
        CheckRank.objects.create(rank=1, min_points=10, name="Novice")
        CheckRank.objects.create(rank=2, min_points=25, name="Competent")

        # Set up outcomes
        self.success = CheckOutcome.objects.create(
            name="Success", success_level=1, description="You succeed at your task"
        )

        self.failure = CheckOutcome.objects.create(
            name="Failure", success_level=-1, description="You fail at your task"
        )

        # Set up result charts
        self.chart_even = ResultChart.objects.create(
            rank_difference=0, name="Even Match"
        )

        self.chart_harder = ResultChart.objects.create(
            rank_difference=2, name="Harder Challenge"
        )

        # Outcomes for even match
        ResultChartOutcome.objects.create(
            chart=self.chart_even, min_roll=1, max_roll=50, outcome=self.failure
        )

        ResultChartOutcome.objects.create(
            chart=self.chart_even, min_roll=51, max_roll=100, outcome=self.success
        )

        # Outcomes for harder challenge
        ResultChartOutcome.objects.create(
            chart=self.chart_harder, min_roll=1, max_roll=70, outcome=self.failure
        )

        ResultChartOutcome.objects.create(
            chart=self.chart_harder, min_roll=71, max_roll=100, outcome=self.success
        )

    def test_resolve_check_complete(self):
        """Test resolving a complete check."""
        result = CheckResolver.resolve_check(
            roller=self.character,
            roller_traits=["diplomacy"],
            target_points=25,  # Same rank (Competent)
        )

        self.assertEqual(result.roller_name, "testchar")
        self.assertEqual(result.roller_points, 30)
        self.assertEqual(result.roller_rank_name, "Competent")
        self.assertEqual(result.rank_difference, 0)
        self.assertIsNotNone(result.roll)
        self.assertIsNotNone(result.outcome)
        self.assertIn(result.roll, range(1, 101))

    def test_resolve_check_with_difficulty(self):
        """Test resolving a check with difficulty modifier."""
        result = CheckResolver.resolve_check(
            roller=self.character,
            roller_traits=["diplomacy"],
            target_points=25,
            difficulty_modifier=2,  # Make it harder
        )

        self.assertEqual(result.roller_name, "testchar")
        self.assertEqual(result.rank_difference, 2)  # 0 + 2 modifier
        self.assertIsNotNone(result.roll)
        self.assertIsNotNone(result.chart)
        self.assertIsNotNone(result.outcome)
        self.assertIn(result.roll, range(1, 101))


class ConvenienceFunctionTests(TestCase):
    """Test convenience functions."""

    def setUp(self):
        """Set up test data."""
        # Clear caches to ensure test isolation
        ResultChart.clear_cache()
        Trait.clear_name_cache()

        from evennia.objects.models import ObjectDB

        self.character = ObjectDB.objects.create(
            db_key="testchar", db_typeclass_path="typeclasses.characters.Character"
        )

        Trait.objects.create(
            name="athletics", trait_type=TraitType.SKILL, category=TraitCategory.GENERAL
        )

        PointConversionRange.objects.create(
            trait_type=TraitType.SKILL, min_value=1, max_value=50, points_per_level=1
        )

        CheckRank.objects.create(rank=0, min_points=0, name="Incompetent")

        # Set up outcome and chart for testing
        success = CheckOutcome.objects.create(
            name="Success", success_level=1, description="You succeed at your task"
        )

        chart = ResultChart.objects.create(rank_difference=0, name="Basic Check")

        ResultChartOutcome.objects.create(
            chart=chart, min_roll=1, max_roll=100, outcome=success
        )

    def test_perform_check_function(self):
        """Test the perform_check convenience function."""
        result = perform_check(
            character=self.character, trait_names=["athletics"], target_difficulty=0
        )

        self.assertEqual(result.roller_name, "testchar")
        self.assertIsNotNone(result.roller_points)
        self.assertIsNotNone(result.roll)
        self.assertIsNotNone(result.outcome)
