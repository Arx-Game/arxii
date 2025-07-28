"""
Account-level commands for ArxII.

These commands handle account management, character switching, and OOC functionality.
They should NOT use flows - account management is OOC and uses standard Django patterns.
"""

from commands.account.cmdset import AccountCmdSet

__all__ = ["AccountCmdSet"]
