"""Evennia command overrides for communication."""

from __future__ import annotations

from typing import Any, ClassVar

from evennia import Command
from evennia.utils import search

from actions.definitions.communication import PoseAction, SayAction, WhisperAction
from commands.command import ArxCommand
from commands.exceptions import CommandError
from commands.frontend import FrontendMetadataMixin
from commands.frontend_types import UsageEntry
from world.roster.models import RosterEntry


class CmdSay(ArxCommand):
    """Speak aloud to the room."""

    key = "say"
    locks = "cmd:all()"
    action = SayAction()

    def resolve_action_args(self) -> dict[str, Any]:
        text = (self.args or "").strip()
        if not text:
            msg = "Say what?"
            raise CommandError(msg)
        return {"text": text}


class CmdWhisper(FrontendMetadataMixin, ArxCommand):
    """Whisper something to a target."""

    usage: ClassVar[list[UsageEntry]] = [
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
        },
    ]

    key = "whisper"
    locks = "cmd:all()"
    action = WhisperAction()

    def resolve_action_args(self) -> dict[str, Any]:
        args = (self.args or "").strip()
        if "=" not in args:
            msg = "Usage: whisper <target>=<text>"
            raise CommandError(msg)
        target_name, text = args.split("=", 1)
        target_name = target_name.strip()
        text = text.strip()
        if not target_name or not text:
            msg = "Usage: whisper <target>=<text>"
            raise CommandError(msg)
        target = self.caller.search(target_name)
        if not target:
            msg = f"Could not find '{target_name}'."
            raise CommandError(msg)
        return {"target": target, "text": text}


class CmdPage(FrontendMetadataMixin, Command):  # ty: ignore[invalid-base]
    """Send a private message to the player of a character."""

    usage: ClassVar[list[UsageEntry]] = [
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
        },
    ]

    key = "page"
    locks = "cmd:all()"
    help_category = "Account"

    def func(self) -> None:
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
            _ = character.roster_entry
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
    aliases: ClassVar[list[str]] = ["emote"]
    locks = "cmd:all()"
    action = PoseAction()

    def resolve_action_args(self) -> dict[str, Any]:
        text = (self.args or "").strip()
        if not text:
            msg = "Pose what?"
            raise CommandError(msg)
        return {"text": text}
