"""Evennia command overrides for communication."""

from evennia import Command
from evennia.utils import search

from commands.command import ArxCommand
from commands.dispatchers import TargetTextDispatcher, TextDispatcher
from commands.frontend import FrontendMetadataMixin
from commands.handlers.base import BaseHandler
from world.roster.models import RosterEntry


class CmdSay(ArxCommand):
    """Speak aloud to the room."""

    key = "say"
    locks = "cmd:all()"
    dispatchers = [TextDispatcher(r"^(?P<text>.+)$", BaseHandler(flow_name="say"))]


class CmdWhisper(FrontendMetadataMixin, ArxCommand):
    """Whisper something to a target."""

    usage = [
        {
            "prompt": "whisper character=message",
            "params_schema": {
                "character": {
                    "type": "string",
                    "widget": "room-character-search",
                    "options_endpoint": "/api/characters/room/",
                },
                "message": {"type": "string"},
            },
        }
    ]

    key = "whisper"
    locks = "cmd:all()"
    dispatchers = [
        TargetTextDispatcher(
            r"^(?P<target>[^=]+)=(?P<text>.+)$",
            BaseHandler(flow_name="whisper"),
        )
    ]


class CmdPage(FrontendMetadataMixin, Command):
    """Send a private message to the player of a character."""

    usage = [
        {
            "prompt": "page character=message",
            "params_schema": {
                "character": {
                    "type": "string",
                    "widget": "character-search",
                    "options_endpoint": "/api/characters/online/",
                },
                "message": {"type": "string"},
            },
        }
    ]

    key = "page"
    locks = "cmd:all()"
    help_category = "Account"

    def func(self):
        """Execute the page command."""
        if not self.args or "=" not in self.args:
            self.caller.msg("Usage: page <character>=<message>")
            return

        charname, text = [part.strip() for part in self.args.split("=", 1)]
        if not charname or not text:
            self.caller.msg("Usage: page <character>=<message>")
            return

        characters = search.object_search(charname, exact=True)
        if not characters:
            self.caller.msg(f"Could not find character '{charname}'.")
            return
        if len(characters) > 1:
            self.caller.msg(f"Multiple characters found matching '{charname}'.")
            return

        character = characters[0]
        try:
            character.roster_entry
        except RosterEntry.DoesNotExist:
            self.caller.msg(f"Character '{charname}' is not on the roster.")
            return

        account = character.active_account
        if not account:
            self.caller.msg(f"Character '{charname}' has no active player.")
            return

        character.msg(f"{self.caller.key} pages: {text}")
        self.caller.msg(f"You page {character.key}: {text}")


class CmdPose(ArxCommand):
    """Emote an action to the room."""

    key = "pose"
    aliases = ["emote"]
    locks = "cmd:all()"
    dispatchers = [TextDispatcher(r"^(?P<text>.+)$", BaseHandler(flow_name="pose"))]
