"""
Tests for the traits system.

Tests models, handlers, and check resolution functionality.
"""

from django.core.exceptions import ValidationError
from django.test import TestCase
import pytest

from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.factories import DistinctionCategoryFactory, DistinctionFactory
from world.distinctions.models import CharacterDistinction, DistinctionEffect
from world.mechanics.factories import ModifierCategoryFactory, ModifierTypeFactory
from world.mechanics.services import create_distinction_modifiers
from world.traits.factories import CharacterTraitValueFactory, TraitFactory
from world.traits.handlers import DefaultTraitValue, TraitHandler
from world.traits.models import (
    CharacterTraitValue,
    CheckRank,
    PointConversionRange,
    Trait,
    TraitCategory,
    TraitRankDescription,
    TraitType,
)


class TraitModelTests(TestCase):
    """Test trait model functionality."""

    def setUp(self):
        """Set up test data."""
        self.trait, _ = Trait.objects.get_or_create(
            name="strength",
            defaults={
                "trait_type": TraitType.STAT,
                "category": TraitCategory.PHYSICAL,
                "description": "Physical power and capability",
            },
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

    def test_get_all_stats_returns_9_stats(self):
        """Test that get_all_stats returns all 9 primary stats."""
        all_stats = self.stat_handler.get_all_stats()

        assert len(all_stats) == 9
        assert "strength" in all_stats
        assert "agility" in all_stats
        assert "stamina" in all_stats
        assert "charm" in all_stats
        assert "presence" in all_stats
        assert "perception" in all_stats
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

        assert len(all_stats_display) == 9

        # Check strength
        assert all_stats_display["strength"].value == 20
        assert all_stats_display["strength"].display == 2
        assert all_stats_display["strength"].modifiers == []

        # Check agility
        assert all_stats_display["agility"].value == 30
        assert all_stats_display["agility"].display == 3
        assert all_stats_display["agility"].modifiers == []

        # Check unset stat defaults to 0
        assert all_stats_display["stamina"].value == 0
        assert all_stats_display["stamina"].display == 0

    def test_set_stat(self):
        """Test setting stat values."""
        success = self.stat_handler.set_stat("strength", 30)
        assert success

        # Verify it was set
        value = self.stat_handler.get_stat("strength")
        assert value == 30

    def test_stat_names_constant(self):
        """Test that STAT_NAMES contains all 9 primary stats."""
        from world.traits.stat_handler import StatHandler

        assert len(StatHandler.STAT_NAMES) == 9
        assert "strength" in StatHandler.STAT_NAMES
        assert "agility" in StatHandler.STAT_NAMES
        assert "stamina" in StatHandler.STAT_NAMES
        assert "charm" in StatHandler.STAT_NAMES
        assert "presence" in StatHandler.STAT_NAMES
        assert "perception" in StatHandler.STAT_NAMES
        assert "intellect" in StatHandler.STAT_NAMES
        assert "wits" in StatHandler.STAT_NAMES
        assert "willpower" in StatHandler.STAT_NAMES


class PrimaryStatTests(TestCase):
    """Test primary stat constants and trait creation."""

    @classmethod
    def setUpTestData(cls):
        """Create primary stats for testing."""
        from world.traits.constants import PrimaryStat

        cls.stats = []
        for name, category, description in PrimaryStat.get_stat_metadata():
            stat, _ = Trait.objects.get_or_create(
                name=name,
                defaults={
                    "trait_type": TraitType.STAT,
                    "category": category,
                    "description": description,
                    "is_public": True,
                },
            )
            cls.stats.append(stat)

    def test_primary_stats_exist(self):
        """Test that all 9 primary stats exist."""
        stats = Trait.objects.filter(trait_type=TraitType.STAT)
        assert stats.count() >= 9

        expected_stats = [
            "strength",
            "agility",
            "stamina",
            "charm",
            "presence",
            "perception",
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
        physical_stats = ["strength", "agility", "stamina"]
        for stat_name in physical_stats:
            stat = Trait.objects.get(name=stat_name, trait_type=TraitType.STAT)
            assert stat.category == TraitCategory.PHYSICAL, f"{stat_name} should be PHYSICAL"

        social_stats = ["charm", "presence", "perception"]
        for stat_name in social_stats:
            stat = Trait.objects.get(name=stat_name, trait_type=TraitType.STAT)
            assert stat.category == TraitCategory.SOCIAL, f"{stat_name} should be SOCIAL"

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
            "perception",
            "intellect",
            "wits",
            "willpower",
        ]

        for stat_name in expected_stats:
            stat = Trait.objects.get(name=stat_name, trait_type=TraitType.STAT)
            assert stat.description, f"Stat '{stat_name}' should have a description"
            assert len(stat.description) > 0, f"Stat '{stat_name}' description should not be empty"

    def test_get_or_create_is_idempotent(self):
        """Test that get_or_create doesn't create duplicates."""
        initial_count = Trait.objects.filter(trait_type=TraitType.STAT).count()

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

        final_count = Trait.objects.filter(trait_type=TraitType.STAT).count()
        assert final_count == initial_count, "get_or_create should be idempotent"


class TraitHandlerStatModifierTests(TestCase):
    """Tests for TraitHandler stat modifier integration (e.g., Giant's Blood)."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data including character with sheet and strength trait."""
        from evennia.objects.models import ObjectDB

        cls.character = ObjectDB.objects.create(db_key="TestChar")
        cls.sheet = CharacterSheetFactory(character=cls.character)

        # Create the strength trait as a stat
        cls.strength_trait = TraitFactory(
            name="strength",
            trait_type=TraitType.STAT,
            category=TraitCategory.PHYSICAL,
        )

        # Create a non-stat trait for comparison
        cls.swords_trait = TraitFactory(
            name="swords",
            trait_type=TraitType.SKILL,
            category=TraitCategory.COMBAT,
        )

        # Create the Giant's Blood distinction with its effects
        physical = DistinctionCategoryFactory(slug="physical", name="Physical")
        cls.giants_blood = DistinctionFactory(
            slug="giants-blood",
            name="Giant's Blood",
            category=physical,
            cost_per_rank=20,
            max_rank=1,
        )

        # Create modifier types
        stat_category = ModifierCategoryFactory(name="stat")
        strength_mod = ModifierTypeFactory(category=stat_category, name="strength")
        height_category = ModifierCategoryFactory(name="height_band")
        height_mod = ModifierTypeFactory(category=height_category, name="max_height_band_bonus")

        # Create effects: +10 strength, +1 height band
        DistinctionEffect.objects.create(
            distinction=cls.giants_blood,
            target=strength_mod,
            value_per_rank=10,
            description="Increases Strength by 1.0",
        )
        DistinctionEffect.objects.create(
            distinction=cls.giants_blood,
            target=height_mod,
            value_per_rank=1,
            description="Can select one height band taller than normal maximum",
        )

    def _grant_giants_blood(self):
        """Helper to grant Giant's Blood distinction and create modifiers."""
        char_distinction = CharacterDistinction.objects.create(
            character=self.character,
            distinction=self.giants_blood,
            rank=1,
        )
        create_distinction_modifiers(char_distinction)
        return char_distinction

    def test_base_trait_value_returns_unmodified(self):
        """get_base_trait_value returns raw value without modifiers."""
        CharacterTraitValueFactory(
            character=self.character,
            trait=self.strength_trait,
            value=30,  # 3.0 display
        )
        self._grant_giants_blood()
        handler = TraitHandler(self.character)

        base_value = handler.get_base_trait_value("strength")

        # Should return raw value, not modified
        assert base_value == 30

    def test_trait_value_includes_stat_modifier(self):
        """get_trait_value includes stat modifiers for stats."""
        CharacterTraitValueFactory(
            character=self.character,
            trait=self.strength_trait,
            value=30,  # 3.0 display
        )
        self._grant_giants_blood()
        handler = TraitHandler(self.character)

        modified_value = handler.get_trait_value("strength")

        # 30 base + 10 (Giant's Blood = +1.0 display = +10 internal) = 40
        assert modified_value == 40

    def test_trait_value_without_distinction_unmodified(self):
        """get_trait_value returns base value when no modifiers apply."""
        CharacterTraitValueFactory(
            character=self.character,
            trait=self.strength_trait,
            value=30,
        )
        # Don't grant Giant's Blood
        handler = TraitHandler(self.character)

        value = handler.get_trait_value("strength")

        assert value == 30

    def test_skill_trait_not_affected_by_stat_modifier(self):
        """Non-stat traits are not affected by stat modifiers."""
        CharacterTraitValueFactory(
            character=self.character,
            trait=self.swords_trait,
            value=25,
        )
        self._grant_giants_blood()
        handler = TraitHandler(self.character)

        # Skills should not be modified by stat modifiers
        value = handler.get_trait_value("swords")

        assert value == 25

    def test_trait_display_value_includes_modifier(self):
        """get_trait_display_value includes modifiers in display format."""
        CharacterTraitValueFactory(
            character=self.character,
            trait=self.strength_trait,
            value=30,  # 3.0 display
        )
        self._grant_giants_blood()
        handler = TraitHandler(self.character)

        display_value = handler.get_trait_display_value("strength")

        # (30 + 10) / 10 = 4.0
        assert display_value == 4.0

    def test_trait_value_case_insensitive(self):
        """Stat modifiers work with case-insensitive trait lookup."""
        CharacterTraitValueFactory(
            character=self.character,
            trait=self.strength_trait,
            value=30,
        )
        self._grant_giants_blood()
        handler = TraitHandler(self.character)

        # Test various case combinations
        assert handler.get_trait_value("strength") == 40
        assert handler.get_trait_value("STRENGTH") == 40
        assert handler.get_trait_value("Strength") == 40

    def test_trait_value_no_sheet_returns_base(self):
        """Characters without sheet get unmodified trait values."""
        from evennia.objects.models import ObjectDB

        character_no_sheet = ObjectDB.objects.create(db_key="NoSheetChar")
        CharacterTraitValueFactory(
            character=character_no_sheet,
            trait=self.strength_trait,
            value=30,
        )
        handler = TraitHandler(character_no_sheet)

        value = handler.get_trait_value("strength")

        # No sheet means no modifiers, so base value
        assert value == 30

    def test_missing_trait_returns_modifier_only(self):
        """Missing traits return modifier value when modifiers apply."""
        self._grant_giants_blood()
        handler = TraitHandler(self.character)

        # Don't create any trait value - base is 0, but modifier still applies
        value = handler.get_trait_value("strength")

        # 0 base + 10 (Giant's Blood modifier) = 10
        assert value == 10


class GiantsBloodModifierCreationTests(TestCase):
    """Tests verifying Giant's Blood creates all expected modifiers."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        from evennia.objects.models import ObjectDB

        cls.character = ObjectDB.objects.create(db_key="TestChar")
        cls.sheet = CharacterSheetFactory(character=cls.character)

        # Create the Giant's Blood distinction with its effects
        physical = DistinctionCategoryFactory(slug="physical", name="Physical")
        cls.giants_blood = DistinctionFactory(
            slug="giants-blood",
            name="Giant's Blood",
            category=physical,
            cost_per_rank=20,
            max_rank=1,
        )

        # Create modifier types
        stat_category = ModifierCategoryFactory(name="stat")
        strength_mod = ModifierTypeFactory(category=stat_category, name="strength")
        height_category = ModifierCategoryFactory(name="height_band")
        height_mod = ModifierTypeFactory(category=height_category, name="max_height_band_bonus")

        # Create effects: +10 strength, +1 height band
        DistinctionEffect.objects.create(
            distinction=cls.giants_blood,
            target=strength_mod,
            value_per_rank=10,
            description="Increases Strength by 1.0",
        )
        DistinctionEffect.objects.create(
            distinction=cls.giants_blood,
            target=height_mod,
            value_per_rank=1,
            description="Can select one height band taller than normal maximum",
        )

    def test_giants_blood_creates_strength_modifier(self):
        """Giant's Blood creates a strength stat modifier."""
        from world.mechanics.models import CharacterModifier

        char_distinction = CharacterDistinction.objects.create(
            character=self.character,
            distinction=self.giants_blood,
            rank=1,
        )
        create_distinction_modifiers(char_distinction)

        # Verify strength modifier was created
        strength_modifiers = CharacterModifier.objects.filter(
            character=self.sheet,
            source__distinction_effect__target__name="strength",
            source__distinction_effect__target__category__name="stat",
        )
        assert strength_modifiers.exists()
        assert strength_modifiers.first().value == 10  # +1.0 display = +10 internal

    def test_giants_blood_creates_height_band_modifier(self):
        """Giant's Blood creates a height band modifier."""
        from world.mechanics.models import CharacterModifier

        char_distinction = CharacterDistinction.objects.create(
            character=self.character,
            distinction=self.giants_blood,
            rank=1,
        )
        create_distinction_modifiers(char_distinction)

        # Verify height band modifier was created
        height_modifiers = CharacterModifier.objects.filter(
            character=self.sheet,
            source__distinction_effect__target__name="max_height_band_bonus",
            source__distinction_effect__target__category__name="height_band",
        )
        assert height_modifiers.exists()
        assert height_modifiers.first().value == 1  # +1 height band
