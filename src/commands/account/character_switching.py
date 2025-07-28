"""
Character switching commands for ArxII multisession account system.
"""

from evennia import Command


class CmdIC(Command):
    """
    Switch to controlling a character.

    Usage:
        @ic <character name>
        ic <character name>

    Switch the current session to control one of your available characters.
    You can have multiple sessions each controlling different characters.

    Examples:
        @ic Ariel
        ic Lysander
    """

    key = "@ic"
    aliases = ["ic"]
    locks = "cmd:all()"
    help_category = "Account"

    def func(self):
        """Execute the character switching."""
        if not self.args:
            self.caller.msg("Usage: @ic <character name>")
            return

        # Find the character by name
        char_name = self.args.strip()
        available_chars = self.account.get_available_characters()

        # Search for matching character
        target_char = None
        for char in available_chars:
            if char.name.lower() == char_name.lower():
                target_char = char
                break

        if not target_char:
            # Try partial match
            matches = [
                char
                for char in available_chars
                if char.name.lower().startswith(char_name.lower())
            ]
            if len(matches) == 1:
                target_char = matches[0]
            elif len(matches) > 1:
                char_list = ", ".join([char.name for char in matches])
                self.caller.msg(f"Multiple matches: {char_list}")
                return
            else:
                available_names = ", ".join([char.name for char in available_chars])
                self.caller.msg(
                    f"Character '{char_name}' not found. Available: {available_names}"
                )
                return

        # Try to puppet the character in this session
        success, message = self.account.puppet_character_in_session(
            target_char, self.session
        )
        self.caller.msg(message)


class CmdCharacters(Command):
    """
    List your available characters.

    Usage:
        @characters
        chars

    Shows all characters you have access to play, along with their current
    status (whether they're being controlled in another session).
    """

    key = "@characters"
    aliases = ["chars", "characters"]
    locks = "cmd:all()"
    help_category = "Account"

    def func(self):
        """List available characters."""
        available_chars = self.account.get_available_characters()
        puppeted_chars = self.account.get_puppeted_characters()

        if not available_chars:
            self.caller.msg(
                "You have no available characters. Contact staff for character access."
            )
            return

        self.caller.msg("Your available characters:")
        for char in available_chars:
            status = " (playing)" if char in puppeted_chars else ""
            self.caller.msg(f"  {char.name}{status}")

        available_sessions = self.account.get_available_sessions()
        if available_sessions:
            session_count = len(available_sessions)
            self.caller.msg(
                f"\nYou have {session_count} session(s) available for character control."
            )
            self.caller.msg("Use '@ic <character>' to control a character.")
