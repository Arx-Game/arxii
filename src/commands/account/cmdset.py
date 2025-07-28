"""
Account command set for ArxII.
"""

from evennia import CmdSet

from commands.account.account_info import CmdAccount
from commands.account.character_switching import CmdCharacters, CmdIC


class AccountCmdSet(CmdSet):
    """
    Command set available to accounts (not characters).
    These are OOC commands for account management.
    """

    key = "account_cmdset"

    def at_cmdset_creation(self):
        """Populate the cmdset."""
        self.add(CmdIC)
        self.add(CmdCharacters)
        self.add(CmdAccount)
