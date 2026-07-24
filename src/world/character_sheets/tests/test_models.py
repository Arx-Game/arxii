"""
Tests for character sheets models.

Tests focus on custom methods and behaviors, not standard Django functionality.
"""

from unittest.mock import MagicMock, patch

from django.core.exceptions import ValidationError
from django.test import TestCase
import pytest

from world.character_sheets.factories import (
    CharacterFactory,
    CharacterSheetFactory,
    GenderFactory,
    ObjectDisplayDataFactory,
)
from world.character_sheets.models import CharacterSheet
from world.character_sheets.types import MaritalStatus
from world.classes.factories import CharacterClassLevelFactory
from world.conditions.factories import CapabilityTypeFactory
from world.conditions.services import get_effective_capability_value
from world.mechanics.factories import ObjectPropertyFactory, PropertyFactory


class CharacterSheetModelTests(TestCase):
    """Test CharacterSheet model custom functionality."""

    def setUp(self):
        """Set up test data."""
        # Flush SharedMemoryModel caches to prevent test pollution
        CharacterSheet.flush_instance_cache()
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)

    def test_character_sheet_creation(self):
        """Test creating a character sheet."""
        assert self.sheet.character == self.character
        assert self.sheet.age >= 18  # From factory validator
        # Gender is a nullable FK - factory creates without gender
        assert self.sheet.gender is None
        assert self.sheet.marital_status == MaritalStatus.SINGLE

    def test_character_sheet_with_gender(self):
        """Test creating a character sheet with gender FK."""
        gender = GenderFactory(key="male", display_name="Male")
        sheet = CharacterSheetFactory(character=CharacterFactory(), gender=gender)
        assert sheet.gender == gender
        assert sheet.gender.display_name == "Male"

    def test_character_sheet_str_representation(self):
        """Test string representation."""
        expected = f"Sheet for {self.character.db_key}"
        assert str(self.sheet) == expected

    def test_age_validation_constraints(self):
        """Test age validation works correctly."""
        # Test minimum age validation through model clean
        # Use a different character to avoid identity mapper returning the cached sheet
        new_char = CharacterFactory()
        sheet = CharacterSheet(character=new_char, age=15)
        with pytest.raises(ValidationError):
            sheet.full_clean()

    def test_social_rank_validation_constraints(self):
        """Test social rank validation works correctly."""
        # Test social rank bounds
        # Use a different character to avoid identity mapper returning the cached sheet
        new_char = CharacterFactory()
        sheet = CharacterSheet(character=new_char, social_rank=25)
        with pytest.raises(ValidationError):
            sheet.full_clean()


class ObjectDisplayDataModelTests(TestCase):
    """Test ObjectDisplayData model custom methods."""

    def setUp(self):
        """Set up test data."""
        self.character = CharacterFactory()
        self.display_data = ObjectDisplayDataFactory(
            object=self.character,
            longname="Sir TestChar the Bold",
            colored_name="|cTestChar|n",
            permanent_description="A tall warrior with piercing eyes.",
            temporary_description="Currently disguised as a merchant.",
        )

    def test_get_display_description_temporary_override(self):
        """Test that temporary description overrides permanent."""
        result = self.display_data.get_display_description()
        assert result == "Currently disguised as a merchant."

    def test_get_display_description_permanent_fallback(self):
        """Test fallback to permanent description."""
        self.display_data.temporary_description = ""
        result = self.display_data.get_display_description()
        assert result == "A tall warrior with piercing eyes."

    def test_get_display_description_empty_fallback(self):
        """Test behavior with no descriptions."""
        self.display_data.permanent_description = ""
        self.display_data.temporary_description = ""
        result = self.display_data.get_display_description()
        assert result == ""

    def test_get_display_name_colored_name_priority(self):
        """Test colored name has priority."""
        result = self.display_data.get_display_name(include_colored=True)
        assert result == "|cTestChar|n"

    def test_get_display_name_no_colored_flag(self):
        """Test skipping colored name when flag is False."""
        result = self.display_data.get_display_name(include_colored=False)
        assert result == "Sir TestChar the Bold"

    def test_get_display_name_longname_fallback(self):
        """Test longname fallback."""
        self.display_data.colored_name = ""
        result = self.display_data.get_display_name()
        assert result == "Sir TestChar the Bold"

    def test_get_display_name_character_key_final_fallback(self):
        """Test final fallback to object key."""
        self.display_data.colored_name = ""
        self.display_data.longname = ""
        result = self.display_data.get_display_name()
        assert result == self.character.db_key


class CharacterSheetPronounTests(TestCase):
    """Test pronoun fields on CharacterSheet."""

    def test_pronoun_fields_exist(self):
        """Test CharacterSheet has pronoun fields with defaults."""
        character = CharacterFactory()
        sheet = CharacterSheetFactory(character=character)

        assert sheet.pronoun_subject == "they"
        assert sheet.pronoun_object == "them"
        assert sheet.pronoun_possessive == "their"

    def test_pronoun_fields_settable(self):
        """Test pronoun fields can be set to custom values."""
        character = CharacterFactory()
        sheet = CharacterSheetFactory(
            character=character,
            pronoun_subject="he",
            pronoun_object="him",
            pronoun_possessive="his",
        )
        assert sheet.pronoun_subject == "he"
        assert sheet.pronoun_object == "him"
        assert sheet.pronoun_possessive == "his"


class CharacterSheetPrimaryPersonaTest(TestCase):
    def test_primary_persona_returns_primary_when_exists(self) -> None:
        from world.scenes.constants import PersonaType
        from world.scenes.models import Persona

        # Build a character with an identity + sheet pointing at the same character
        identity = CharacterSheetFactory()
        character = identity.character
        # CharacterSheetFactory ensures a sheet exists and links the primary.
        sheet = character.sheet_data
        primary = identity.primary_persona
        # Add an ESTABLISHED persona linked to the same sheet
        Persona.objects.create(
            character_sheet=sheet,
            name="Alter Ego",
            persona_type=PersonaType.ESTABLISHED,
        )
        assert sheet.primary_persona == primary

    def test_primary_persona_raises_when_no_primary(self) -> None:
        from world.scenes.models import Persona

        # Opt out of the factory's PRIMARY persona creation to exercise the
        # "no primary exists" branch of the cached_property.
        sheet = CharacterSheetFactory(primary_persona=False)
        with self.assertRaises(Persona.DoesNotExist):
            _ = sheet.primary_persona


class CharacterSheetDisplayDelegatesTest(TestCase):
    """Tests that CharacterSheet.display_* delegate to primary_persona."""

    def test_display_ic_delegates_to_primary_persona(self) -> None:
        from world.character_sheets.factories import (
            CharacterSheetFactory,
        )

        sheet = CharacterSheetFactory()
        identity = CharacterSheetFactory(character=sheet.character)
        primary = identity.primary_persona
        primary.character_sheet = sheet
        primary.name = "Bob"
        primary.save()
        assert sheet.display_ic() == "Bob"

    def test_display_with_history_delegates(self) -> None:
        from world.character_sheets.factories import (
            CharacterSheetFactory,
        )

        sheet = CharacterSheetFactory()
        identity = CharacterSheetFactory(character=sheet.character)
        primary = identity.primary_persona
        primary.character_sheet = sheet
        primary.name = "Alice"
        primary.save()
        # No tenure, so result is just the name
        assert sheet.display_with_history() == "Alice"

    def test_display_to_staff_delegates(self) -> None:
        from world.character_sheets.factories import (
            CharacterSheetFactory,
        )

        sheet = CharacterSheetFactory()
        identity = CharacterSheetFactory(character=sheet.character)
        primary = identity.primary_persona
        primary.character_sheet = sheet
        primary.name = "Charlie"
        primary.save()
        # No roster_entry → name only
        assert sheet.display_to_staff() == "Charlie"


class CurrentLevelTests(TestCase):
    """Tests for CharacterSheet.current_level and cached_character_class_levels."""

    def test_current_level_is_zero_without_class_assignments(self):
        sheet = CharacterSheetFactory()
        self.assertEqual(sheet.current_level, 0)

    def test_current_level_returns_highest_across_classes(self):
        sheet = CharacterSheetFactory()
        CharacterClassLevelFactory(character=sheet, level=3)
        CharacterClassLevelFactory(character=sheet, level=5)
        CharacterClassLevelFactory(character=sheet, level=2)
        self.assertEqual(sheet.current_level, 5)

    def test_current_level_is_cached(self):
        sheet = CharacterSheetFactory()
        CharacterClassLevelFactory(character=sheet, level=5)

        # First access populates cache.
        first = sheet.current_level
        self.assertEqual(first, 5)

        # Now add a higher level; without invalidation, cached value persists.
        CharacterClassLevelFactory(character=sheet, level=7)
        self.assertEqual(sheet.current_level, 5, "Cached value should persist")

        # Invalidate and confirm the cache re-derives the new higher value.
        sheet.invalidate_class_level_cache()
        self.assertEqual(sheet.current_level, 7)


class InControlPropertyTests(TestCase):
    """Tests for CharacterSheet.in_control derived property (slice 4)."""

    def setUp(self):
        CharacterSheet.flush_instance_cache()
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)

    def test_in_control_true_with_no_alters_behavior_conditions(self):
        self.assertIs(self.sheet.in_control, True)

    def test_in_control_false_with_alters_behavior_condition(self):
        fake_condition = MagicMock()
        fake_condition.condition.category.alters_behavior = True
        with patch.object(self.sheet.character.conditions, "active", return_value=[fake_condition]):
            self.assertIs(self.sheet.in_control, False)

    def test_in_control_true_when_only_non_altering_conditions(self):
        fake_condition = MagicMock()
        fake_condition.condition.category.alters_behavior = False
        with patch.object(self.sheet.character.conditions, "active", return_value=[fake_condition]):
            self.assertIs(self.sheet.in_control, True)


class CachedAchievementsHeldTests(TestCase):
    """Tests for CharacterSheet.cached_achievements_held and invalidation."""

    def test_cached_achievements_held_empty_when_none_earned(self):
        from world.character_sheets.factories import CharacterSheetFactory

        sheet = CharacterSheetFactory()
        self.assertEqual(sheet.cached_achievements_held, set())

    def test_cached_achievements_held_contains_earned_achievement(self):
        from world.achievements.factories import AchievementFactory, CharacterAchievementFactory
        from world.character_sheets.factories import CharacterSheetFactory

        sheet = CharacterSheetFactory()
        achievement = AchievementFactory()
        CharacterAchievementFactory(character_sheet=sheet, achievement=achievement)

        held = sheet.cached_achievements_held
        self.assertIn(achievement, held)

    def test_cached_achievements_held_excludes_other_characters(self):
        from world.achievements.factories import AchievementFactory, CharacterAchievementFactory
        from world.character_sheets.factories import CharacterSheetFactory

        sheet_a = CharacterSheetFactory()
        sheet_b = CharacterSheetFactory()
        achievement = AchievementFactory()
        CharacterAchievementFactory(character_sheet=sheet_b, achievement=achievement)

        self.assertNotIn(achievement, sheet_a.cached_achievements_held)

    def test_invalidate_achievement_cache_clears_cached_property(self):
        from world.achievements.factories import AchievementFactory, CharacterAchievementFactory
        from world.character_sheets.factories import CharacterSheetFactory

        sheet = CharacterSheetFactory()
        achievement = AchievementFactory()

        # Populate the cache (empty).
        self.assertEqual(sheet.cached_achievements_held, set())

        # Grant the achievement and invalidate.
        CharacterAchievementFactory(character_sheet=sheet, achievement=achievement)
        sheet.invalidate_achievement_cache()

        # Now the cache reflects the mutation.
        self.assertIn(achievement, sheet.cached_achievements_held)


class CachedActiveConditionTemplatesTests(TestCase):
    """Tests for CharacterSheet.cached_active_condition_templates and invalidation."""

    def test_cached_active_condition_templates_empty_when_none_active(self):
        from world.character_sheets.factories import CharacterSheetFactory

        sheet = CharacterSheetFactory()
        self.assertEqual(sheet.cached_active_condition_templates, set())

    def test_cached_active_condition_templates_contains_active_condition(self):
        from world.character_sheets.factories import CharacterSheetFactory
        from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory

        sheet = CharacterSheetFactory()
        template = ConditionTemplateFactory()
        ConditionInstanceFactory(target=sheet.character, condition=template)

        active = sheet.cached_active_condition_templates
        self.assertIn(template, active)

    def test_cached_active_condition_templates_excludes_suppressed(self):
        from world.character_sheets.factories import CharacterSheetFactory
        from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory

        sheet = CharacterSheetFactory()
        template = ConditionTemplateFactory()
        ConditionInstanceFactory(target=sheet.character, condition=template, is_suppressed=True)

        active = sheet.cached_active_condition_templates
        self.assertNotIn(template, active)

    def test_cached_active_condition_templates_excludes_other_characters(self):
        from world.character_sheets.factories import CharacterSheetFactory
        from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory

        sheet_a = CharacterSheetFactory()
        sheet_b = CharacterSheetFactory()
        template = ConditionTemplateFactory()
        ConditionInstanceFactory(target=sheet_b.character, condition=template)

        self.assertNotIn(template, sheet_a.cached_active_condition_templates)

    def test_invalidate_condition_cache_clears_cached_property(self):
        from world.character_sheets.factories import CharacterSheetFactory
        from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory

        sheet = CharacterSheetFactory()
        template = ConditionTemplateFactory()

        # Populate the cache (empty).
        self.assertEqual(sheet.cached_active_condition_templates, set())

        # Apply condition and invalidate.
        ConditionInstanceFactory(target=sheet.character, condition=template)
        sheet.invalidate_condition_cache()

        # Now the cache reflects the mutation.
        self.assertIn(template, sheet.cached_active_condition_templates)


class CharacterSheetCapabilityPropertyProtocolTests(TestCase):
    """CharacterSheet conforms to HasCapabilities/HasProperties (#1794)."""

    def test_effective_capability_matches_get_effective_capability_value(self) -> None:
        sheet = CharacterSheetFactory()
        capability = CapabilityTypeFactory(innate_baseline=3)
        self.assertEqual(
            sheet.effective_capability(capability),
            get_effective_capability_value(sheet, capability),
        )

    def test_has_property_true_via_object_property(self) -> None:
        sheet = CharacterSheetFactory()
        prop = PropertyFactory()
        ObjectPropertyFactory(object=sheet.character, property=prop)
        self.assertTrue(sheet.has_property(prop))

    def test_has_property_true_via_persona_authored_property(self) -> None:
        sheet = CharacterSheetFactory()
        prop = PropertyFactory()
        sheet.primary_persona.properties.add(prop)
        self.assertTrue(sheet.has_property(prop))

    def test_has_property_false_when_absent(self) -> None:
        sheet = CharacterSheetFactory()
        prop = PropertyFactory()
        self.assertFalse(sheet.has_property(prop))
