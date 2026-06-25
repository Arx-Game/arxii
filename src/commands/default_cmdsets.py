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
from commands.account.prompt_reply import CmdPromptReply
from commands.account.sheet import CmdSheet
from commands.combat import CmdClashCommit, CmdDeclareTechnique
from commands.combat_maneuvers import CmdCombat
from commands.consent import (
    CmdAccept,
    CmdDeceive,
    CmdDeny,
    CmdEntrance,
    CmdFlirt,
    CmdIntimidate,
    CmdPerform,
    CmdPersuade,
    CmdRestoreSense,
)
from commands.door import CmdLock, CmdUnlock
from commands.endorse import CmdEndorse, CmdPoses
from commands.evennia_overrides.builder import CmdDig, CmdLink, CmdOpen, CmdUnlink
from commands.evennia_overrides.communication import (
    CmdEmit,
    CmdMutter,
    CmdPage,
    CmdPemit,
    CmdPose,
    CmdSay,
    CmdTabletalk,
    CmdWhisper,
)
from commands.evennia_overrides.items import (
    CmdPut,
    CmdRemove,
    CmdUndress,
    CmdUse,
    CmdWear,
    CmdWithdraw,
)
from commands.evennia_overrides.movement import CmdDrop, CmdGet, CmdGive, CmdHome
from commands.evennia_overrides.perception import CmdInventory, CmdLook
from commands.fashion import CmdJudgePresentation
from commands.gemit import CmdGemit
from commands.imbue import CmdImbue
from commands.locations import CmdManageRoom
from commands.offer_response import CmdDecline
from commands.ritual import CmdRitual
from commands.scene import CmdScene
from commands.social.blocking import (
    CmdBlock,
    CmdBlockList,
    CmdMute,
    CmdShareBlock,
    CmdUnblock,
    CmdUnmute,
)
from commands.social.entrance_flourish import CmdEnter, CmdFlourish
from commands.social.grievance import CmdGrievance
from commands.social.soul_tether import CmdSineater, CmdTether
from commands.social.tidings import CmdTidings
from commands.weave import CmdWeaveThread


class CharacterCmdSet(default_cmds.CharacterCmdSet):
    """
    The `CharacterCmdSet` contains general in-game commands like `look`,
    `get`, etc available on in-game Character objects. It is merged with
    the `AccountCmdSet` when an Account puppets a Character.
    """

    key = "DefaultCharacter"

    def at_cmdset_creation(self) -> None:
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

        # Each command is a thin telnet shell; register them by iterating a
        # tuple so this method stays well under ruff's statement ceiling
        # (PLR0915) as the command roster grows.
        command_classes = (
            CmdLook,
            CmdGet,
            CmdDrop,
            CmdGive,
            CmdWear,
            CmdRemove,
            CmdUndress,
            CmdPut,
            CmdWithdraw,
            CmdUse,
            CmdHome,
            CmdInventory,
            CmdSay,
            CmdWhisper,
            CmdPose,
            CmdEmit,
            CmdPemit,
            CmdMutter,
            CmdTabletalk,
            CmdLock,
            CmdUnlock,
            CmdRitual,
            CmdWeaveThread,
            CmdImbue,
            CmdEnter,
            CmdFlourish,
            CmdEndorse,
            CmdPoses,
            CmdJudgePresentation,
            CmdIntimidate,
            CmdAccept,
            CmdDecline,
            CmdDeny,
            CmdPersuade,
            CmdDeceive,
            CmdFlirt,
            CmdPerform,
            CmdEntrance,
            CmdRestoreSense,
            CmdDig,
            CmdOpen,
            CmdLink,
            CmdUnlink,
            # #1278 — block/mute social controls (the telnet face of the persona menu).
            CmdBlock,
            CmdUnblock,
            CmdShareBlock,
            CmdMute,
            CmdUnmute,
            CmdBlockList,
            # Soul Tether lifecycle commands (#1343)
            CmdTether,
            CmdSineater,
            # #1429 — the telnet face of the secret-victim grievance prompt.
            CmdGrievance,
            # #1450 — the pull/browse face of the public-reaction tidings feed.
            CmdTidings,
            # #1450 — the staff push face: hand-authored gemits scoped by reach.
            CmdGemit,
            # Unified scene-adaptive cast (#1351)
            CmdDeclareTechnique,
            # Clash contribution (#1451)
            CmdClashCommit,
            # Shared combat verbs: combat <subverb> (#1453, #1452)
            CmdCombat,
            # Scene lifecycle telnet command (#1445)
            CmdScene,
            # #1470 — owner-gated room editor (name/description/public-private).
            CmdManageRoom,
        )
        for command_cls in command_classes:
            self.add(command_cls())


class AccountCmdSet(default_cmds.AccountCmdSet):
    """
    This is the cmdset available to the Account at all times. It is
    combined with the `CharacterCmdSet` when the Account puppets a
    Character. It holds game-account-specific commands, channel
    commands, etc.
    """

    key = "DefaultAccount"

    def at_cmdset_creation(self) -> None:
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
        self.add(CmdPromptReply())


class UnloggedinCmdSet(default_cmds.UnloggedinCmdSet):
    """
    Command set available to the Session before being logged in.  This
    holds commands like creating a new account, logging in, etc.
    """

    key = "DefaultUnloggedin"

    def at_cmdset_creation(self) -> None:
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

    def at_cmdset_creation(self) -> None:
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
