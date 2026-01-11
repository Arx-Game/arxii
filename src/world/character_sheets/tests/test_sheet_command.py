"""
Tests for the @sheet command.

Tests the sheet command's output formatting and content.
"""

from unittest.mock import MagicMock

from django.test import TestCase

from commands.account.sheet import CmdSheet
from world.character_sheets.factories import (
    BasicCharacteristicsSetupFactory,
    CharacterFactory,
    CharacterSheetFactory,
    CharacterWithCharacteristicsFactory,
    GenderFactory,
)
from world.roster.factories import FamilyFactory


class SheetCommandTests(TestCase):
    """Test @sheet command functionality."""

    def setUp(self):
        """Set up test data."""
        # Create basic characteristics for tests
        BasicCharacteristicsSetupFactory.create()

        # Create test character with full data
        self.char_data = CharacterWithCharacteristicsFactory.create(
            character_name="TestHero",
            characteristics={
                "eye_color": "blue",
                "hair_color": "brown",
                "height": "tall",
                "skin_tone": "fair",
            },
        )
        self.character = self.char_data["character"]
        self.sheet = self.char_data["sheet"]

        # Update sheet with more test data
        self.gender = GenderFactory(key="female", display_name="Female")
        self.family = FamilyFactory(name="Stormwind")
        self.sheet.age = 25
        self.sheet.gender = self.gender
        self.sheet.concept = "A brave knight"
        self.sheet.family = self.family
        self.sheet.vocation = "Knight"
        self.sheet.social_rank = 3
        self.sheet.birthday = "Spring 15th"
        self.sheet.quote = "Honor above all!"
        self.sheet.personality = "Brave and noble, always stands up for the weak."
        self.sheet.background = "Born into nobility, trained as a knight from childhood."
        self.sheet.save()

        # Update display data (handler will auto-create it)
        # Access the display data through the handler to ensure it exists
        display_data = self.character.item_data._get_display_data()
        display_data.longname = "Dame TestHero of Stormwind"
        display_data.colored_name = "|cTestHero|n"
        display_data.permanent_description = "A tall, noble warrior with piercing blue eyes."
        display_data.save()

    def _create_command_with_caller(self, caller=None, args=""):
        """Create a command instance with mocked account caller."""
        if caller is None:
            caller = self.character

        # Mock the account caller
        mock_caller = MagicMock()
        mock_caller.key = f"Account_{caller.key}"
        mock_caller.name = f"Account_{caller.key}"
        mock_caller.is_staff = False

        # Mock puppet (current character)
        mock_caller.puppet = caller

        # Mock available characters method
        mock_caller.get_available_characters.return_value = [caller]

        # Mock search method to return our character
        mock_caller.search.return_value = self.character if args else None

        # Create command
        cmd = CmdSheet()
        cmd.caller = mock_caller
        cmd.args = args

        return cmd, mock_caller

    def test_sheet_command_basic_info_displayed(self):
        """Test that basic character information is displayed."""
        cmd, mock_caller = self._create_command_with_caller()

        # Execute command
        cmd.func()

        # Get the output
        assert mock_caller.msg.called
        output = mock_caller.msg.call_args[0][0]

        # Check that basic information is present
        assert "TestHero" in output
        assert "Age: 25" in output
        assert "Gender: Female" in output
        assert "Concept: A brave knight" in output
        assert "Family: Stormwind" in output
        assert "Vocation: Knight" in output
        assert "Social Rank: 3" in output
        assert "Birthday: Spring 15th" in output

    def test_sheet_command_physical_characteristics(self):
        """Test that physical characteristics are displayed."""
        cmd, mock_caller = self._create_command_with_caller()

        cmd.func()

        output = mock_caller.msg.call_args[0][0]

        # Check physical characteristics section
        assert "Physical Characteristics" in output
        assert "Eye Color: Blue" in output
        assert "Hair Color: Brown" in output
        assert "Height: Tall" in output
        assert "Skin Tone: Fair" in output

    def test_sheet_command_description_displayed(self):
        """Test that character description is displayed."""
        cmd, mock_caller = self._create_command_with_caller()

        cmd.func()

        output = mock_caller.msg.call_args[0][0]

        # Check description
        assert "Description" in output
        assert "A tall, noble warrior with piercing blue eyes." in output

    def test_sheet_command_names_section(self):
        """Test that names section displays correctly."""
        cmd, mock_caller = self._create_command_with_caller()

        cmd.func()

        output = mock_caller.msg.call_args[0][0]

        # Check names section
        assert "Names" in output
        assert "Full Name: Dame TestHero of Stormwind" in output
        assert "Colored Name: |cTestHero|n" in output

    def test_sheet_command_quote_and_personality(self):
        """Test that quote and personality are displayed."""
        cmd, mock_caller = self._create_command_with_caller()

        cmd.func()

        output = mock_caller.msg.call_args[0][0]

        # Check quote and personality
        assert "Quote" in output
        assert '"Honor above all!"' in output
        assert "Personality" in output
        assert "Brave and noble" in output

    def test_sheet_command_background_displayed(self):
        """Test that background is displayed."""
        cmd, mock_caller = self._create_command_with_caller()

        cmd.func()

        output = mock_caller.msg.call_args[0][0]

        # Check background
        assert "Background" in output
        assert "Born into nobility" in output

    def test_sheet_command_staff_only_fields_hidden(self):
        """Test that staff-only fields are hidden from normal users."""
        # Add staff-only data
        self.sheet.real_age = 100
        self.sheet.real_concept = "Secret vampire"
        self.sheet.obituary = "Died heroically"
        self.sheet.additional_desc = "Staff notes here"
        self.sheet.save()

        cmd, mock_caller = self._create_command_with_caller()

        cmd.func()

        output = mock_caller.msg.call_args[0][0]

        # Staff-only fields should not appear
        assert "Real Age" not in output
        assert "Real Concept" not in output
        assert "Obituary" not in output
        assert "Additional Description" not in output
        assert "Secret vampire" not in output
        assert "Staff notes here" not in output

    def test_sheet_command_staff_only_fields_shown_to_staff(self):
        """Test that staff-only fields are shown to staff users."""
        # Add staff-only data
        self.sheet.real_age = 100
        self.sheet.real_concept = "Secret vampire"
        self.sheet.obituary = "Died heroically"
        self.sheet.additional_desc = "Staff notes here"
        self.sheet.save()

        cmd, mock_caller = self._create_command_with_caller()
        mock_caller.is_staff = True

        cmd.func()

        output = mock_caller.msg.call_args[0][0]

        # Staff-only fields should appear
        assert "Real Age: 100" in output
        assert "Real Concept: Secret vampire" in output
        assert "Obituary (Staff Only)" in output
        assert "Additional Description (Staff Only)" in output
        assert "Staff notes here" in output

    def test_sheet_command_no_characteristics_message(self):
        """Test message when character has no physical characteristics."""
        # Create character without characteristics
        character = CharacterFactory()
        CharacterSheetFactory(character=character)

        cmd, mock_caller = self._create_command_with_caller(caller=character)

        cmd.func()

        output = mock_caller.msg.call_args[0][0]

        # Should show "no characteristics" message
        assert "No physical characteristics set" in output

    def test_sheet_command_text_wrapping(self):
        """Test that long text is properly wrapped."""
        # Create very long personality text
        long_personality = (
            "This is a very long personality description that should be wrapped " * 10
        )
        self.sheet.personality = long_personality
        self.sheet.save()

        cmd, mock_caller = self._create_command_with_caller()

        cmd.func()

        output = mock_caller.msg.call_args[0][0]

        # Check that text is present and appears to be wrapped (no extremely long lines)
        assert "This is a very long personality" in output
        # Split into lines and check that no line is excessively long
        lines = output.split("\n")
        for line in lines:
            assert len(line) <= 80, f"Line too long: {line}"

    def test_sheet_command_long_text_truncation(self):
        """Test that very long personality/background text is truncated."""
        # Create text longer than 200 characters
        long_text = "A" * 250
        self.sheet.personality = long_text
        self.sheet.save()

        cmd, mock_caller = self._create_command_with_caller()

        cmd.func()

        output = mock_caller.msg.call_args[0][0]

        # Should be truncated with ellipsis
        assert "..." in output
        # Should not contain the full long text
        assert "A" * 250 not in output

    def test_sheet_command_with_target_character(self):
        """Test viewing another character's sheet."""
        cmd, mock_caller = self._create_command_with_caller(args="TestHero")

        cmd.func()

        # Should have called search with the character name
        mock_caller.search.assert_called_once_with("TestHero", global_search=True)

        # Should display the sheet
        assert mock_caller.msg.called
        output = mock_caller.msg.call_args[0][0]
        assert "TestHero" in output

    def test_sheet_command_target_not_found(self):
        """Test behavior when target character is not found."""
        cmd, mock_caller = self._create_command_with_caller(args="NonExistentChar")
        mock_caller.search.return_value = None

        cmd.func()

        # Should not call msg for the sheet (search handles the error message)
        # Just verify search was called
        mock_caller.search.assert_called_once_with(
            "NonExistentChar",
            global_search=True,
        )

    def test_sheet_command_non_character_target(self):
        """Test behavior when target is not a character."""
        # Create a mock object without sheet_data
        mock_object = MagicMock()
        mock_object.name = "NotACharacter"
        del mock_object.sheet_data  # Remove the attribute

        cmd, mock_caller = self._create_command_with_caller(args="NotACharacter")
        mock_caller.search.return_value = mock_object

        cmd.func()

        # Should show error message
        mock_caller.msg.assert_called_with("NotACharacter is not a character.")

    def test_wrap_text_method(self):
        """Test the _wrap_text helper method."""
        cmd = CmdSheet()

        # Test normal wrapping
        text = "This is a test string that should be wrapped at appropriate points"
        result = cmd._wrap_text(text, width=20)

        # Should be multiple lines
        assert len(result) > 1
        # No line should exceed width
        for line in result:
            assert len(line) <= 20
        # All text should be preserved
        assert " ".join(result) == text

    def test_wrap_text_empty_input(self):
        """Test _wrap_text with empty input."""
        cmd = CmdSheet()

        result = cmd._wrap_text("")
        assert result == []

        result = cmd._wrap_text(None)
        assert result == []

    def test_sheet_command_with_classes(self):
        """Test that character classes are displayed in the sheet."""
        from world.classes.models import CharacterClass, CharacterClassLevel

        # Create test classes
        warrior_class = CharacterClass.objects.create(
            name="Warrior",
            description="A mighty fighter",
            minimum_level=1,
        )
        scholar_class = CharacterClass.objects.create(
            name="Scholar",
            description="A learned individual",
            minimum_level=1,
        )

        # Assign classes to character
        CharacterClassLevel.objects.create(
            character=self.character,
            character_class=warrior_class,
            level=3,
            is_primary=True,
        )
        CharacterClassLevel.objects.create(
            character=self.character,
            character_class=scholar_class,
            level=6,  # Elite eligible
        )

        cmd, mock_caller = self._create_command_with_caller()

        cmd.func()

        output = mock_caller.msg.call_args[0][0]

        # Check classes section
        assert "Classes" in output
        assert "Scholar: Level 6 |g(Elite Eligible)|n" in output
        assert "Warrior: Level 3 |y(Primary)|n" in output

    def test_sheet_command_no_classes_section_when_empty(self):
        """Test that classes section doesn't appear when character has no classes."""
        # Create character without classes
        character = CharacterFactory()
        CharacterSheetFactory(character=character)

        cmd, mock_caller = self._create_command_with_caller(caller=character)

        cmd.func()

        output = mock_caller.msg.call_args[0][0]

        # Should not show classes section
        assert "Classes" not in output
