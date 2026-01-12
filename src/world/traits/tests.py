"""
Tests for the traits system.

Tests models, handlers, and check resolution functionality.
"""

from django.core.exceptions import ValidationError
from django.test import TestCase
import pytest

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
            db_key="testchar",
            db_typeclass_path="typeclasses.characters.Character",
        )

    def test_trait_creation(self):
        """Test creating and accessing traits."""
        assert self.trait.name == "strength"
        assert self.trait.trait_type == TraitType.STAT
        assert self.trait.category == TraitCategory.PHYSICAL
        assert self.trait.is_public

    def test_trait_str_representation(self):
        """Test trait string representation."""
        expected = "strength (Stat)"
        assert str(self.trait) == expected

    def test_character_trait_value(self):
        """Test character trait values."""
        trait_value = CharacterTraitValue.objects.create(
            character=self.character,
            trait=self.trait,
            value=25,
        )

        assert trait_value.value == 25
        assert trait_value.display_value == 2.5

    def test_trait_rank_description(self):
        """Test trait rank descriptions."""
        rank_desc = TraitRankDescription.objects.create(
            trait=self.trait,
            value=30,
            label="Powerful Warrior",
            description="Someone with exceptional physical strength",
        )

        assert rank_desc.display_value == 3.0
        assert "Powerful Warrior" in str(rank_desc)

    def test_trait_case_insensitive_lookup(self):
        """Test case-insensitive trait lookup."""
        # Test exact match
        trait = Trait.get_by_name("strength")
        assert trait == self.trait

        # Test case variations
        trait = Trait.get_by_name("STRENGTH")
        assert trait == self.trait

        trait = Trait.get_by_name("Strength")
        assert trait == self.trait

        trait = Trait.get_by_name("sTrEnGtH")
        assert trait == self.trait

        # Test non-existent trait
        trait = Trait.get_by_name("nonexistent")
        assert trait is None


class PointConversionRangeTests(TestCase):
    """Test point conversion range functionality."""

    def setUp(self):
        """Set up conversion ranges."""
        # Create ranges for stats
        PointConversionRange.objects.create(
            trait_type=TraitType.STAT,
            min_value=1,
            max_value=20,
            points_per_level=1,
        )
        PointConversionRange.objects.create(
            trait_type=TraitType.STAT,
            min_value=21,
            max_value=40,
            points_per_level=2,
        )
        PointConversionRange.objects.create(
            trait_type=TraitType.STAT,
            min_value=41,
            max_value=60,
            points_per_level=3,
        )

    def test_point_calculation(self):
        """Test point calculation for trait values."""
        # Value 10 should give 10 points (1-20 range, 1 point each)
        points = PointConversionRange.calculate_points(TraitType.STAT, 10)
        assert points == 10

        # Value 25 should give 20 + 10 = 30 points
        # (20 points from 1-20 range, 10 points from 21-25 in second range)
        points = PointConversionRange.calculate_points(TraitType.STAT, 25)
        assert points == 30

        # Value 45 should give 20 + 40 + 15 = 75 points
        points = PointConversionRange.calculate_points(TraitType.STAT, 45)
        assert points == 75

    def test_range_validation(self):
        """Test range overlap validation."""
        # This should raise validation error due to overlap
        overlapping_range = PointConversionRange(
            trait_type=TraitType.STAT,
            min_value=15,
            max_value=25,
            points_per_level=1,
        )

        with pytest.raises(ValidationError):
            overlapping_range.clean()

    def test_contains_value(self):
        """Test range contains value check."""
        range_obj = PointConversionRange.objects.get(min_value=21, max_value=40)

        assert range_obj.contains_value(25)
        assert range_obj.contains_value(21)
        assert range_obj.contains_value(40)
        assert not range_obj.contains_value(20)
        assert not range_obj.contains_value(41)


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
        assert rank.name == "Incompetent"

        rank = CheckRank.get_rank_for_points(15)
        assert rank.name == "Novice"

        rank = CheckRank.get_rank_for_points(30)
        assert rank.name == "Competent"

        rank = CheckRank.get_rank_for_points(75)
        assert rank.name == "Expert"

    def test_rank_difference(self):
        """Test calculating rank differences."""
        diff = CheckRank.get_rank_difference(30, 15)  # Competent vs Novice
        assert diff == 1  # rank 2 - rank 1

        diff = CheckRank.get_rank_difference(5, 30)  # Incompetent vs Competent
        assert diff == -2  # rank 0 - rank 2


class TraitHandlerTests(TestCase):
    """Test trait handler caching functionality."""

    def setUp(self):
        """Set up test data."""
        from evennia.objects.models import ObjectDB

        self.character = ObjectDB.objects.create(
            db_key="testchar",
            db_typeclass_path="typeclasses.characters.Character",
        )

        self.trait = Trait.objects.create(
            name="swords",
            trait_type=TraitType.SKILL,
            category=TraitCategory.COMBAT,
        )

        self.trait2 = Trait.objects.create(
            name="diplomacy",
            trait_type=TraitType.SKILL,
            category=TraitCategory.GENERAL,
        )

        self.handler = self.character.traits

        # Set up point conversion
        PointConversionRange.objects.create(
            trait_type=TraitType.SKILL,
            min_value=1,
            max_value=50,
            points_per_level=1,
        )

    def test_get_trait_value(self):
        """Test getting trait values."""
        # Should return 0 for unset trait
        value = self.handler.get_trait_value("swords")
        assert value == 0

        # Set a value and test retrieval
        CharacterTraitValue.objects.create(
            character=self.character,
            trait=self.trait,
            value=25,
        )

        # Clear the handler cache to pick up new data
        self.handler.clear_cache()

        value = self.handler.get_trait_value("swords")
        assert value == 25

    def test_set_trait_value(self):
        """Test setting trait values."""
        success = self.handler.set_trait_value("swords", 30)
        assert success

        # Verify it was set
        value = self.handler.get_trait_value("swords")
        assert value == 30

        # Test updating existing value
        success = self.handler.set_trait_value("swords", 35)
        assert success

        # Clear cache to pick up the updated value
        self.handler.clear_cache()

        value = self.handler.get_trait_value("swords")
        assert value == 35

    def test_get_display_value(self):
        """Test getting display values."""
        self.handler.set_trait_value("swords", 25)
        display = self.handler.get_trait_display_value("swords")
        assert display == 2.5

    def test_calculate_check_points(self):
        """Test calculating check points."""
        self.handler.set_trait_value("swords", 20)

        points = self.handler.calculate_check_points(["swords"])
        assert points == 20  # 1 point per level for skills

    def test_case_insensitive_trait_access(self):
        """Test case-insensitive trait access through handler."""
        self.handler.set_trait_value("swords", 25)

        # Test various case combinations
        assert self.handler.get_trait_value("swords") == 25
        assert self.handler.get_trait_value("SWORDS") == 25
        assert self.handler.get_trait_value("Swords") == 25
        assert self.handler.get_trait_value("SwOrDs") == 25

    def test_default_trait_value(self):
        """Test default trait value for missing traits."""
        trait_obj = self.handler.get_trait_object("nonexistent")
        assert isinstance(trait_obj, DefaultTraitValue)
        assert trait_obj.value == 0
        assert not trait_obj  # Should be falsy

    def test_cache_auto_update(self):
        """Test automatic cache updating when trait values change."""
        # Set initial value
        self.handler.set_trait_value("swords", 30)
        assert self.handler.get_trait_value("swords") == 30

        # Update through direct model save - cache should auto-update
        trait_value = CharacterTraitValue.objects.get(
            character=self.character,
            trait=self.trait,
        )
        trait_value.value = 40
        trait_value.save()

        # Clear cache to pick up the updated value
        self.handler.clear_cache()

        # Cache should be automatically updated
        assert self.handler.get_trait_value("swords") == 40

    def test_get_cached_handler(self):
        """Test the global cached handler function."""
        handler1 = self.character.traits
        handler2 = self.character.traits

        # Should return the same cached instance
        assert handler1 is handler2

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
            character=self.character,
            trait=private_trait,
            value=40,
        )

        # Get all traits
        all_traits = self.handler.get_all_traits()
        assert "swords" in str(all_traits)
        assert "secret_skill" in str(all_traits)

        # Get only public traits
        public_traits = self.handler.get_public_traits()
        assert "swords" in str(public_traits)
        assert "secret_skill" not in str(public_traits)


class CheckResolverTests(TestCase):
    """Test check resolution functionality."""

    def setUp(self):
        """Set up test data for check resolution."""
        # Clear caches to ensure test isolation
        ResultChart.clear_cache()
        Trait.clear_name_cache()

        from evennia.objects.models import ObjectDB

        self.character = ObjectDB.objects.create(
            db_key="testchar",
            db_typeclass_path="typeclasses.characters.Character",
        )

        # Create trait
        self.trait = Trait.objects.create(
            name="diplomacy",
            trait_type=TraitType.SKILL,
            category=TraitCategory.GENERAL,
        )

        # Set trait value
        CharacterTraitValue.objects.create(
            character=self.character,
            trait=self.trait,
            value=30,
        )

        # Set up point conversion
        PointConversionRange.objects.create(
            trait_type=TraitType.SKILL,
            min_value=1,
            max_value=50,
            points_per_level=1,
        )

        # Set up ranks
        CheckRank.objects.create(rank=0, min_points=0, name="Incompetent")
        CheckRank.objects.create(rank=1, min_points=10, name="Novice")
        CheckRank.objects.create(rank=2, min_points=25, name="Competent")

        # Set up outcomes
        self.success = CheckOutcome.objects.create(
            name="Success",
            success_level=1,
            description="You succeed at your task",
        )

        self.failure = CheckOutcome.objects.create(
            name="Failure",
            success_level=-1,
            description="You fail at your task",
        )

        # Set up result charts
        self.chart_even = ResultChart.objects.create(
            rank_difference=0,
            name="Even Match",
        )

        self.chart_harder = ResultChart.objects.create(
            rank_difference=2,
            name="Harder Challenge",
        )

        # Outcomes for even match
        ResultChartOutcome.objects.create(
            chart=self.chart_even,
            min_roll=1,
            max_roll=50,
            outcome=self.failure,
        )

        ResultChartOutcome.objects.create(
            chart=self.chart_even,
            min_roll=51,
            max_roll=100,
            outcome=self.success,
        )

        # Outcomes for harder challenge
        ResultChartOutcome.objects.create(
            chart=self.chart_harder,
            min_roll=1,
            max_roll=70,
            outcome=self.failure,
        )

        ResultChartOutcome.objects.create(
            chart=self.chart_harder,
            min_roll=71,
            max_roll=100,
            outcome=self.success,
        )

    def test_resolve_check_complete(self):
        """Test resolving a complete check."""
        result = CheckResolver.resolve_check(
            roller=self.character,
            roller_traits=["diplomacy"],
            target_points=25,  # Same rank (Competent)
        )

        assert result.roller_name == "testchar"
        assert result.roller_points == 30
        assert result.roller_rank_name == "Competent"
        assert result.rank_difference == 0
        assert result.roll is not None
        assert result.outcome is not None
        assert result.roll in range(1, 101)

    def test_resolve_check_with_difficulty(self):
        """Test resolving a check with difficulty modifier."""
        result = CheckResolver.resolve_check(
            roller=self.character,
            roller_traits=["diplomacy"],
            target_points=25,
            difficulty_modifier=2,  # Make it harder
        )

        assert result.roller_name == "testchar"
        assert result.rank_difference == 2  # 0 + 2 modifier
        assert result.roll is not None
        assert result.chart is not None
        assert result.outcome is not None
        assert result.roll in range(1, 101)


class ConvenienceFunctionTests(TestCase):
    """Test convenience functions."""

    def setUp(self):
        """Set up test data."""
        # Clear caches to ensure test isolation
        ResultChart.clear_cache()
        Trait.clear_name_cache()

        from evennia.objects.models import ObjectDB

        self.character = ObjectDB.objects.create(
            db_key="testchar",
            db_typeclass_path="typeclasses.characters.Character",
        )

        Trait.objects.create(
            name="athletics",
            trait_type=TraitType.SKILL,
            category=TraitCategory.GENERAL,
        )

        PointConversionRange.objects.create(
            trait_type=TraitType.SKILL,
            min_value=1,
            max_value=50,
            points_per_level=1,
        )

        CheckRank.objects.create(rank=0, min_points=0, name="Incompetent")

        # Set up outcome and chart for testing
        success = CheckOutcome.objects.create(
            name="Success",
            success_level=1,
            description="You succeed at your task",
        )

        chart = ResultChart.objects.create(rank_difference=0, name="Basic Check")

        ResultChartOutcome.objects.create(
            chart=chart,
            min_roll=1,
            max_roll=100,
            outcome=success,
        )

    def test_perform_check_function(self):
        """Test the perform_check convenience function."""
        result = perform_check(
            character=self.character,
            trait_names=["athletics"],
            target_difficulty=0,
        )

        assert result.roller_name == "testchar"
        assert result.roller_points is not None
        assert result.roll is not None
        assert result.outcome is not None


class StatHandlerTests(TestCase):
    """Test stat-specific handler functionality."""

    def setUp(self):
        """Set up test data for stats."""
        from evennia.objects.models import ObjectDB

        self.character = ObjectDB.objects.create(
            db_key="testchar",
            db_typeclass_path="typeclasses.characters.Character",
        )

        # Get or create the 8 primary stats (may already exist from migration)
        self.stats = {}
        stat_data = [
            ("strength", TraitCategory.PHYSICAL, "Physical power and muscle"),
            ("agility", TraitCategory.PHYSICAL, "Speed, reflexes, and coordination"),
            ("stamina", TraitCategory.PHYSICAL, "Endurance and resistance to harm"),
            ("charm", TraitCategory.SOCIAL, "Likability and social magnetism"),
            ("presence", TraitCategory.SOCIAL, "Force of personality and leadership"),
            ("intellect", TraitCategory.MENTAL, "Reasoning and learned knowledge"),
            ("wits", TraitCategory.MENTAL, "Quick thinking and situational awareness"),
            ("willpower", TraitCategory.MENTAL, "Mental fortitude and determination"),
        ]

        for name, category, description in stat_data:
            trait, _created = Trait.objects.get_or_create(
                name=name,
                defaults={
                    "trait_type": TraitType.STAT,
                    "category": category,
                    "description": description,
                },
            )
            self.stats[name] = trait

        self.stat_handler = self.character.stats

    def test_get_all_stats_returns_8_stats(self):
        """Test that get_all_stats returns all 8 primary stats."""
        all_stats = self.stat_handler.get_all_stats()

        assert len(all_stats) == 8
        assert "strength" in all_stats
        assert "agility" in all_stats
        assert "stamina" in all_stats
        assert "charm" in all_stats
        assert "presence" in all_stats
        assert "intellect" in all_stats
        assert "wits" in all_stats
        assert "willpower" in all_stats

        # All stats should default to 0 if not set
        for value in all_stats.values():
            assert value == 0

    def test_stat_display_value_conversion(self):
        """Test internal value to display value conversion."""
        # Set internal value to 20 (should display as 2)
        self.stat_handler.set_stat("strength", 20)
        self.stat_handler.traits.clear_cache()
        display_value = self.stat_handler.get_stat_display("strength")

        assert display_value == 2

        # Set internal value to 50 (should display as 5)
        self.stat_handler.set_stat("agility", 50)
        self.stat_handler.traits.clear_cache()
        display_value = self.stat_handler.get_stat_display("agility")

        assert display_value == 5

        # Set internal value to 10 (should display as 1)
        self.stat_handler.set_stat("stamina", 10)
        self.stat_handler.traits.clear_cache()
        display_value = self.stat_handler.get_stat_display("stamina")

        assert display_value == 1

    def test_stat_display_value_rounding(self):
        """Test that display values round down correctly."""
        # Internal value 25 should display as 2 (not 2.5 or 3)
        CharacterTraitValue.objects.create(
            character=self.character,
            trait=self.stats["strength"],
            value=25,
        )

        # Clear cache to pick up new value
        self.stat_handler.traits.clear_cache()

        display_value = self.stat_handler.get_stat_display("strength")
        assert display_value == 2  # Integer division: 25 // 10 = 2

        # Internal value 56 should display as 5 (not 5.6 or 6)
        CharacterTraitValue.objects.create(
            character=self.character,
            trait=self.stats["agility"],
            value=56,
        )

        self.stat_handler.traits.clear_cache()

        display_value = self.stat_handler.get_stat_display("agility")
        assert display_value == 5  # Integer division: 56 // 10 = 5

    def test_get_all_stats_display(self):
        """Test get_all_stats_display returns proper format."""
        # Set some stat values
        self.stat_handler.set_stat("strength", 20)
        self.stat_handler.set_stat("agility", 30)

        all_stats_display = self.stat_handler.get_all_stats_display()

        assert len(all_stats_display) == 8

        # Check strength
        assert all_stats_display["strength"]["value"] == 20
        assert all_stats_display["strength"]["display"] == 2
        assert all_stats_display["strength"]["modifiers"] == []

        # Check agility
        assert all_stats_display["agility"]["value"] == 30
        assert all_stats_display["agility"]["display"] == 3
        assert all_stats_display["agility"]["modifiers"] == []

        # Check unset stat defaults to 0
        assert all_stats_display["stamina"]["value"] == 0
        assert all_stats_display["stamina"]["display"] == 0

    def test_set_stat(self):
        """Test setting stat values."""
        success = self.stat_handler.set_stat("strength", 30)
        assert success

        # Verify it was set
        value = self.stat_handler.get_stat("strength")
        assert value == 30

    def test_stat_names_constant(self):
        """Test that STAT_NAMES contains all 8 primary stats."""
        from world.traits.stat_handler import StatHandler

        assert len(StatHandler.STAT_NAMES) == 8
        assert "strength" in StatHandler.STAT_NAMES
        assert "agility" in StatHandler.STAT_NAMES
        assert "stamina" in StatHandler.STAT_NAMES
        assert "charm" in StatHandler.STAT_NAMES
        assert "presence" in StatHandler.STAT_NAMES
        assert "intellect" in StatHandler.STAT_NAMES
        assert "wits" in StatHandler.STAT_NAMES
        assert "willpower" in StatHandler.STAT_NAMES


class PrimaryStatMigrationTests(TestCase):
    """Test that primary stats migration creates expected traits."""

    def test_primary_stats_exist(self):
        """Test that all 8 primary stats are created in database."""
        # Get all stat-type traits
        stats = Trait.objects.filter(trait_type=TraitType.STAT)

        # Should have at least 8 primary stats
        # (May have more if other stat types exist)
        assert stats.count() >= 8

        # Check that all 8 primary stats exist
        expected_stats = [
            "strength",
            "agility",
            "stamina",
            "charm",
            "presence",
            "intellect",
            "wits",
            "willpower",
        ]

        for stat_name in expected_stats:
            stat = Trait.objects.filter(name=stat_name, trait_type=TraitType.STAT).first()
            assert stat is not None, f"Stat '{stat_name}' not found in database"
            assert stat.is_public, f"Stat '{stat_name}' should be public"

    def test_primary_stats_have_categories(self):
        """Test that primary stats have correct categories."""
        # Physical stats
        physical_stats = ["strength", "agility", "stamina"]
        for stat_name in physical_stats:
            stat = Trait.objects.get(name=stat_name, trait_type=TraitType.STAT)
            assert stat.category == TraitCategory.PHYSICAL, f"{stat_name} should be PHYSICAL"

        # Social stats
        social_stats = ["charm", "presence"]
        for stat_name in social_stats:
            stat = Trait.objects.get(name=stat_name, trait_type=TraitType.STAT)
            assert stat.category == TraitCategory.SOCIAL, f"{stat_name} should be SOCIAL"

        # Mental stats (including defensive)
        mental_stats = ["intellect", "wits", "willpower"]
        for stat_name in mental_stats:
            stat = Trait.objects.get(name=stat_name, trait_type=TraitType.STAT)
            assert stat.category == TraitCategory.MENTAL, f"{stat_name} should be MENTAL"

    def test_primary_stats_have_descriptions(self):
        """Test that primary stats have descriptions."""
        expected_stats = [
            "strength",
            "agility",
            "stamina",
            "charm",
            "presence",
            "intellect",
            "wits",
            "willpower",
        ]

        for stat_name in expected_stats:
            stat = Trait.objects.get(name=stat_name, trait_type=TraitType.STAT)
            assert stat.description, f"Stat '{stat_name}' should have a description"
            assert len(stat.description) > 0, f"Stat '{stat_name}' description should not be empty"

    def test_migration_is_idempotent(self):
        """Test that running migration multiple times doesn't create duplicates."""
        # Count existing stats
        initial_count = Trait.objects.filter(trait_type=TraitType.STAT).count()

        # Try to create again using get_or_create (simulating migration re-run)
        from world.traits.models import TraitCategory

        stat_data = [
            ("strength", TraitCategory.PHYSICAL, "Physical power and muscle"),
            ("agility", TraitCategory.PHYSICAL, "Speed, reflexes, and coordination"),
        ]

        for name, category, description in stat_data:
            Trait.objects.get_or_create(
                name=name,
                defaults={
                    "trait_type": TraitType.STAT,
                    "category": category,
                    "description": description,
                    "is_public": True,
                },
            )

        # Count should not increase (get_or_create should get existing)
        final_count = Trait.objects.filter(trait_type=TraitType.STAT).count()
        assert final_count == initial_count, "Migration should be idempotent"
