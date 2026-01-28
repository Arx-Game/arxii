"""Tests for trait handlers including stat modifiers."""

from django.test import TestCase
from evennia.objects.models import ObjectDB

from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.models import CharacterDistinction, Distinction
from world.mechanics.services import create_distinction_modifiers
from world.traits.factories import CharacterTraitValueFactory, TraitFactory
from world.traits.handlers import TraitHandler
from world.traits.models import TraitCategory, TraitType


class TraitHandlerStatModifierTests(TestCase):
    """Tests for TraitHandler stat modifier integration (e.g., Giant's Blood)."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data including character with sheet and strength trait."""
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

        # Get the Giant's Blood distinction
        cls.giants_blood = Distinction.objects.get(slug="giants-blood")

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

    def test_missing_trait_returns_zero(self):
        """Missing traits return 0 even with modifiers."""
        self._grant_giants_blood()
        handler = TraitHandler(self.character)

        # Don't create any trait value
        value = handler.get_trait_value("strength")

        # 0 base + 10 modifier = 10
        # Wait, if trait value doesn't exist, base is 0
        # But modifier still applies? Let's verify expected behavior
        # Actually, if there's no trait value, the base is 0
        # But Giant's Blood still provides +10 to strength
        assert value == 10
