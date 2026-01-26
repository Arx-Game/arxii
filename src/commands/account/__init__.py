"""
Account-level commands for ArxII.

These commands handle account management, character switching, and OOC functionality.
They should NOT use flows - account management is OOC and uses standard Django patterns.

Command classes should be imported from their specific modules:
    from commands.account.account_info import CmdAccount
    from commands.account.character_switching import CmdCharacters, CmdIC
"""
