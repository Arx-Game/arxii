"""
Account information commands for ArxII.
"""

from typing import ClassVar

from evennia import Command


class CmdAccount(Command):  # ty: ignore[invalid-base]
    """
    Show account information and settings.

    Usage:
        @account

    Displays your account information, preferences, and current session status.
    This shows OOC account-level information, not character information.
    """

    key = "@account"
    aliases: ClassVar[list[str]] = ["account"]
    locks = "cmd:all()"
    help_category = "Account"

    def func(self):
        """Display account information."""
        account = self.account
        player_data = account.player_data

        # Account header
        self.caller.msg(f"Account Information for {account.username}")
        self.caller.msg("=" * 50)

        # Basic info
        self.caller.msg(f"Display Name: {player_data.display_name}")
        self.caller.msg(f"Email: {account.email}")
        self.caller.msg(f"Last Login: {account.last_login}")
        self.caller.msg(f"Account Created: {account.date_created}")

        # Session info
        sessions = account.sessions.all()
        self.caller.msg(f"\nActive Sessions: {len(sessions)}")

        for i, session in enumerate(sessions, 1):
            puppet_info = f" (controlling {session.puppet.name})" if session.puppet else " (OOC)"
            self.caller.msg(f"  Session {i}: {session.protocol_key}{puppet_info}")

        # Character access
        available_chars = account.get_available_characters()
        puppeted_chars = account.get_puppeted_characters()

        self.caller.msg(f"\nCharacter Access: {len(available_chars)} character(s)")
        if available_chars:
            for char in available_chars:
                status = " (currently playing)" if char in puppeted_chars else ""
                self.caller.msg(f"  {char.name}{status}")

        # Preferences
        self.caller.msg("\nPreferences:")
        self.caller.msg(f"  Hide from watch lists: {player_data.hide_from_watch}")
        self.caller.msg(f"  Private mode: {player_data.private_mode}")

        # Staff info (if staff)
        if account.is_staff:
            self.caller.msg("\nStaff Information:")
            self.caller.msg(f"  Karma: {player_data.karma}")
            if player_data.gm_notes:
                self.caller.msg(f"  GM Notes: {player_data.gm_notes}")
            else:
                self.caller.msg("  GM Notes: None")
