"""
Character sheet display command for ArxII.

Provides the @sheet OOC command to display character demographic and descriptive data.
This is an account-level command for viewing character information out-of-character.
"""

from typing import ClassVar

from evennia import Command


class CmdSheet(Command):  # ty: ignore[invalid-base]
    """
    Display character sheet information (OOC).

    Usage:
        @sheet [character]
        sheet [character]

    Displays the character sheet with demographic information, physical
    characteristics, and descriptive text. If no character is specified,
    shows your currently controlled character's sheet.

    This is an out-of-character command for viewing character information.
    Staff can view any character's sheet. Players can only view sheets
    of characters they control or that are publicly visible.
    """

    key = "@sheet"
    aliases: ClassVar[list[str]] = ["sheet"]
    locks = "cmd:all()"
    help_category = "Account"

    def func(self):
        """Display character sheet information."""
        target = self._get_target_character()
        if not target:
            return

        if not self._validate_target_and_permissions(target):
            return

        sheet_data = target.item_data
        output = self._build_sheet_display(target, sheet_data)
        self.caller.msg("\n".join(output))

    def _get_target_character(self):
        """Get the target character for the sheet command."""
        if self.args.strip():
            # Looking at another character
            return self.caller.search(self.args.strip(), global_search=True)
        # Looking at own character - get from account's current puppet
        try:
            puppet = self.caller.puppet
        except AttributeError:
            puppet = None
        if puppet:
            return puppet
        # Try to get available characters if no current puppet
        try:
            get_available_characters = self.caller.get_available_characters
        except AttributeError:
            get_available_characters = None
        available_chars = get_available_characters() if get_available_characters else []
        if available_chars:
            return available_chars[0]  # Use first available character
        self.caller.msg(
            "You don't have any characters to display a sheet for.",
        )
        return None

    def _validate_target_and_permissions(self, target):
        """Validate target is a character and check permissions."""
        # Check if target is actually a character
        try:
            sheet_data = target.sheet_data
        except AttributeError:
            self.caller.msg(f"{target.name} is not a character.")
            return False
        if sheet_data is None:
            self.caller.msg(f"{target.name} is not a character.")
            return False

        # Permission check - accounts can view sheets of their own characters
        # Staff can view any character's sheet
        # TODO: Add proper permission checking when trust system is implemented
        if not self.caller.is_staff:
            # Non-staff can only view their own characters
            try:
                get_available_characters = self.caller.get_available_characters
            except AttributeError:
                get_available_characters = None
            account_chars = get_available_characters() if get_available_characters else []
            if target not in account_chars:
                self.caller.msg(
                    "You can only view character sheets for your own characters.",
                )
                return False
        return True

    def _build_sheet_display(self, target, sheet_data):
        """Build the complete sheet display."""
        output = []

        # Header
        output.extend(self._build_header(target, sheet_data))

        # Basic Information
        output.extend(self._build_basic_info(sheet_data))

        # Physical Characteristics
        output.extend(self._build_physical_characteristics(sheet_data))

        # Classes
        output.extend(self._build_classes_section(sheet_data))

        # Description
        output.extend(self._build_description(sheet_data))

        # Names
        output.extend(self._build_names_section(target, sheet_data))

        # Quote
        output.extend(self._build_quote_section(sheet_data))

        # Personality and Background
        output.extend(self._build_personality_background(sheet_data))

        # Staff-only sections
        if self.caller.is_staff:
            output.extend(self._build_staff_sections(sheet_data))

        return output

    def _build_header(self, target, sheet_data):
        """Build the header section."""
        display_name = sheet_data.get_display_name()
        if display_name != target.key:
            header = f"Character Sheet for {display_name} ({target.key})"
        else:
            header = f"Character Sheet for {target.key}"

        return [header, "=" * len(header), ""]

    def _build_basic_info(self, sheet_data):
        """Build the basic information section."""
        output = ["|wBasic Information|n", "-" * 20]

        output.append(f"Age: {sheet_data.age}")
        if sheet_data.real_age and self.caller.is_staff:
            output.append(f"Real Age: {sheet_data.real_age} |r(staff only)|n")

        output.append(f"Gender: {sheet_data.gender.title()}")
        output.append(f"Concept: {sheet_data.concept or 'None'}")
        if sheet_data.real_concept and self.caller.is_staff:
            output.append(f"Real Concept: {sheet_data.real_concept} |r(staff only)|n")

        if sheet_data.family:
            output.append(f"Family: {sheet_data.family}")
        if sheet_data.vocation:
            output.append(f"Vocation: {sheet_data.vocation}")

        output.append(f"Social Rank: {sheet_data.social_rank}")
        output.append(f"Marital Status: {sheet_data.marital_status.title()}")

        if sheet_data.birthday:
            output.append(f"Birthday: {sheet_data.birthday}")

        output.append("")
        return output

    def _build_physical_characteristics(self, sheet_data):
        """Build the physical characteristics section."""
        output = ["|wPhysical Characteristics|n", "-" * 25]

        characteristics = []
        if sheet_data.eye_color:
            characteristics.append(f"Eye Color: {sheet_data.eye_color}")
        if sheet_data.hair_color:
            characteristics.append(f"Hair Color: {sheet_data.hair_color}")
        if sheet_data.height:
            characteristics.append(f"Height: {sheet_data.height}")
        if sheet_data.skin_tone:
            characteristics.append(f"Skin Tone: {sheet_data.skin_tone}")

        if characteristics:
            output.extend(characteristics)
        else:
            output.append("No physical characteristics set.")

        output.append("")
        return output

    def _build_classes_section(self, sheet_data):
        """Build the character classes section."""
        classes = sheet_data.classes
        if not classes:
            return []

        output = ["|wClasses|n", "-" * 8]

        for class_level in classes:
            class_name = class_level.character_class.name
            level = class_level.level
            primary_marker = " |y(Primary)|n" if class_level.is_primary else ""
            elite_marker = " |g(Elite Eligible)|n" if class_level.is_elite_eligible else ""
            output.append(f"{class_name}: Level {level}{primary_marker}{elite_marker}")

        output.append("")
        return output

    def _build_description(self, sheet_data):
        """Build the description section."""
        description = sheet_data.get_display_description()
        if not description:
            return []

        output = ["|wDescription|n", "-" * 12]
        desc_lines = self._wrap_text(description, width=78)
        output.extend(desc_lines)
        output.append("")
        return output

    def _build_names_section(self, target, sheet_data):
        """Build the names section."""
        names_section = []
        if sheet_data.longname and sheet_data.longname != target.key:
            names_section.append(f"Full Name: {sheet_data.longname}")
        if sheet_data.colored_name and sheet_data.colored_name != target.key:
            names_section.append(f"Colored Name: {sheet_data.colored_name}")

        # Check for active guise (false names)
        active_guise = sheet_data._get_active_guise()
        if active_guise and active_guise.name != target.key:
            names_section.append(f"Active Guise: {active_guise.name}")
            if active_guise.colored_name and active_guise.colored_name != active_guise.name:
                names_section.append(f"Guise Colored Name: {active_guise.colored_name}")

        if not names_section:
            return []

        output = ["|wNames|n", "-" * 6]
        output.extend(names_section)
        output.append("")
        return output

    def _build_quote_section(self, sheet_data):
        """Build the quote section."""
        if not sheet_data.quote:
            return []

        output = ["|wQuote|n", "-" * 6]
        quote_lines = self._wrap_text(f'"{sheet_data.quote}"', width=78)
        output.extend(quote_lines)
        output.append("")
        return output

    def _build_personality_background(self, sheet_data):
        """Build personality and background sections."""
        output = []
        TRUNCATE_SUFFIX_LENGTH = 3  # "..."

        # Personality (condensed view)
        if sheet_data.personality:
            output.append("|wPersonality|n")
            output.append("-" * 12)
            personality = sheet_data.personality
            MAX_PERSONALITY_LENGTH = 200
            if len(personality) > MAX_PERSONALITY_LENGTH:
                truncate_at = MAX_PERSONALITY_LENGTH - TRUNCATE_SUFFIX_LENGTH
                personality = personality[:truncate_at] + "..."
            personality_lines = self._wrap_text(personality, width=78)
            output.extend(personality_lines)
            output.append("")

        # Background (condensed view)
        if sheet_data.background:
            output.append("|wBackground|n")
            output.append("-" * 11)
            background = sheet_data.background
            MAX_BACKGROUND_LENGTH = 200
            if len(background) > MAX_BACKGROUND_LENGTH:
                background = background[: MAX_BACKGROUND_LENGTH - TRUNCATE_SUFFIX_LENGTH] + "..."
            background_lines = self._wrap_text(background, width=78)
            output.extend(background_lines)
            output.append("")

        return output

    def _build_staff_sections(self, sheet_data):
        """Build staff-only sections."""
        output = []

        if sheet_data.obituary:
            output.append("|rObituary (Staff Only)|n")
            output.append("-" * 21)
            obit_lines = self._wrap_text(sheet_data.obituary, width=78)
            output.extend(obit_lines)
            output.append("")

        if sheet_data.additional_desc:
            output.append("|rAdditional Description (Staff Only)|n")
            output.append("-" * 35)
            additional_lines = self._wrap_text(sheet_data.additional_desc, width=78)
            output.extend(additional_lines)
            output.append("")

        return output

    def _wrap_text(self, text, width=78):
        """
        Simple text wrapping for better display.

        Args:
            text (str): Text to wrap
            width (int): Maximum line width

        Returns:
            list: List of wrapped lines
        """
        if not text:
            return []

        words = text.split()
        lines = []
        current_line: list[str] = []
        current_length = 0

        for word in words:
            # Check if adding this word would exceed width
            word_length = len(word)
            space_length = 1 if current_line else 0

            if current_length + space_length + word_length > width and current_line:
                # Start new line
                lines.append(" ".join(current_line))
                current_line = [word]
                current_length = word_length
            else:
                # Add to current line
                current_line.append(word)
                current_length += space_length + word_length

        # Don't forget the last line
        if current_line:
            lines.append(" ".join(current_line))

        return lines
