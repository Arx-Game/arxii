"""
Command sets

All commands in the game must be grouped in a cmdset.  A given command
can be part of any number of cmdsets and cmdsets can be added/removed
and merged onto entities at runtime.

To create new commands to populate the cmdset, see
`commands/command.py`.

This module wraps the default command sets of Evennia; overloads them
to add/remove commands from the default lineup. You can create your
own cmdsets by inheriting from them or directly from `evennia.CmdSet`.

"""

from evennia import default_cmds

from commands.account.account_info import CmdAccount
from commands.account.character_switching import CmdCharacters, CmdIC
from commands.account.sheet import CmdSheet
from commands.evennia_overrides.communication import CmdPage


class CharacterCmdSet(default_cmds.CharacterCmdSet):
    """
    The `CharacterCmdSet` contains general in-game commands like `look`,
    `get`, etc available on in-game Character objects. It is merged with
    the `AccountCmdSet` when an Account puppets a Character.
    """

    key = "DefaultCharacter"

    def at_cmdset_creation(self):
        """
        Populates the cmdset
        """
        super().at_cmdset_creation()
        # Replace Evennia's basic interaction commands with flow-based versions.
        for cmdname in (
            "look",
            "get",
            "drop",
            "give",
            "home",
            "inventory",
            "say",
            "whisper",
            "pose",
            "emote",
            "dig",
            "open",
            "link",
            "unlink",
        ):
            self.remove(cmdname)

        from commands.door import CmdLock, CmdUnlock
        from commands.evennia_overrides.builder import (
            CmdDig,
            CmdLink,
            CmdOpen,
            CmdUnlink,
        )
        from commands.evennia_overrides.communication import CmdPose, CmdSay, CmdWhisper
        from commands.evennia_overrides.movement import (
            CmdDrop,
            CmdGet,
            CmdGive,
            CmdHome,
        )
        from commands.evennia_overrides.perception import CmdInventory, CmdLook

        self.add(CmdLook())
        self.add(CmdGet())
        self.add(CmdDrop())
        self.add(CmdGive())
        self.add(CmdHome())
        self.add(CmdInventory())
        self.add(CmdSay())
        self.add(CmdWhisper())
        self.add(CmdPose())
        self.add(CmdLock())
        self.add(CmdUnlock())
        self.add(CmdDig())
        self.add(CmdOpen())
        self.add(CmdLink())
        self.add(CmdUnlink())


class AccountCmdSet(default_cmds.AccountCmdSet):
    """
    This is the cmdset available to the Account at all times. It is
    combined with the `CharacterCmdSet` when the Account puppets a
    Character. It holds game-account-specific commands, channel
    commands, etc.
    """

    key = "DefaultAccount"

    def at_cmdset_creation(self):
        """
        Populates the cmdset
        """
        super().at_cmdset_creation()
        for cmdname in ("ic", "characters", "account", "page"):
            self.remove(cmdname)

        self.add(CmdIC())
        self.add(CmdCharacters())
        self.add(CmdAccount())
        self.add(CmdSheet())
        self.add(CmdPage())


class UnloggedinCmdSet(default_cmds.UnloggedinCmdSet):
    """
    Command set available to the Session before being logged in.  This
    holds commands like creating a new account, logging in, etc.
    """

    key = "DefaultUnloggedin"

    def at_cmdset_creation(self):
        """
        Populates the cmdset
        """
        super().at_cmdset_creation()
        #
        # any commands you add below will overload the default ones.
        #


class SessionCmdSet(default_cmds.SessionCmdSet):
    """
    This cmdset is made available on Session level once logged in. It
    is empty by default.
    """

    key = "DefaultSession"

    def at_cmdset_creation(self):
        """
        This is the only method defined in a cmdset, called during
        its creation. It should populate the set with command instances.

        As and example we just add the empty base `Command` object.
        It prints some info.
        """
        super().at_cmdset_creation()
        #
        # any commands you add below will overload the default ones.
        #
