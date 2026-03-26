"""Evennia command overrides for communication."""

from __future__ import annotations

from typing import Any, ClassVar

from django.core.exceptions import ObjectDoesNotExist
from evennia import Command
from evennia.utils import search

from actions.definitions.communication import EmitAction, PoseAction, SayAction, WhisperAction
from commands.command import ArxCommand
from commands.exceptions import CommandError
from commands.frontend import FrontendMetadataMixin
from commands.frontend_types import UsageEntry
from world.roster.models import RosterEntry
from world.scenes.place_models import Place


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
        from commands.parsing import parse_targets_from_text  # noqa: PLC0415

        remaining, targets = parse_targets_from_text(text, self.caller.location)
        result: dict[str, Any] = {"text": remaining or text}
        if targets:
            result["targets"] = targets
        return result


class CmdWhisper(ArxCommand):
    """Whisper something to a target."""

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


class CmdTabletalk(ArxCommand):
    """Send a message to everyone at your current place (table, corner, etc.)."""

    key = "tt"
    aliases: ClassVar[list[str]] = ["tabletalk"]
    locks = "cmd:all()"
    action = PoseAction()

    def resolve_action_args(self) -> dict[str, Any]:
        text = (self.args or "").strip()
        if not text:
            msg = "Tabletalk what?"
            raise CommandError(msg)
        place = self._get_current_place()
        if place is None:
            msg = "You are not at a place. Join one first."
            raise CommandError(msg)
        return {"text": text, "place": place}

    def _get_current_place(self) -> Place | None:
        """Get the place the character is currently at."""
        from world.scenes.place_models import PlacePresence  # noqa: PLC0415

        try:
            identity = self.caller.character_identity
            persona = identity.active_persona
            if persona is None:
                return None
            presence = PlacePresence.objects.filter(persona=persona).first()
            return presence.place if presence else None
        except (AttributeError, ObjectDoesNotExist):
            return None


class CmdPose(ArxCommand):
    """Pose an action to the room (prepends character name)."""

    key = "pose"
    locks = "cmd:all()"
    action = PoseAction()

    def resolve_action_args(self) -> dict[str, Any]:
        text = (self.args or "").strip()
        if not text:
            msg = "Pose what?"
            raise CommandError(msg)
        from commands.parsing import parse_targets_from_text  # noqa: PLC0415

        remaining, targets = parse_targets_from_text(text, self.caller.location)
        result: dict[str, Any] = {"text": remaining or text}
        if targets:
            result["targets"] = targets
        return result


class CmdEmit(ArxCommand):
    """Emit raw text to the room (no character name prepended).

    Classic MUSH emit: the text appears as-is. The interaction metadata
    still records who wrote it, but the content has no automatic prefix.
    """

    key = "emit"
    aliases: ClassVar[list[str]] = ["emote"]
    locks = "cmd:all()"
    action = EmitAction()

    def resolve_action_args(self) -> dict[str, Any]:
        text = (self.args or "").strip()
        if not text:
            msg = "Emit what?"
            raise CommandError(msg)
        from commands.parsing import parse_targets_from_text  # noqa: PLC0415

        remaining, targets = parse_targets_from_text(text, self.caller.location)
        result: dict[str, Any] = {"text": remaining or text}
        if targets:
            result["targets"] = targets
        return result
