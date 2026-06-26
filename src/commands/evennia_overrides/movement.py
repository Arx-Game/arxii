"""Evennia command overrides related to movement and item manipulation."""

from __future__ import annotations

import re
from typing import Any, ClassVar

from actions.definitions.items import TakeOutAction
from actions.definitions.movement import DropAction, GetAction, GiveAction, HomeAction
from commands.command import ArxCommand


class CmdGet(ArxCommand):
    """Pick up an item from the room or take an item out of a container.

    Telnet grammars:
        ``get <item>`` / ``take <item>``                 — pick up from the room
        ``get <item> from <container>``                  — take out of a container
        ``take <item> from <container>`` (alias)
    """

    key = "get"
    aliases: ClassVar[list[str]] = ["take"]
    locks = "cmd:all()"
    action = GetAction()

    def resolve_action_args(self) -> dict[str, Any]:
        args = self.require_args("Get what?")
        # ``from <container>`` form switches to TakeOutAction. Try the
        # connector form first; if it doesn't match, fall back to single-target.
        match = re.match(r"^(.+?)\s+from\s+(.+)$", args, flags=re.IGNORECASE)
        if match:
            item_name = match.group(1).strip()
            container_name = match.group(2).strip()
            container = self.search_or_raise(container_name)
            target = self.search_or_raise(
                item_name,
                location=container,
                not_found_msg=f"Could not find '{item_name}' in '{container_name}'.",
            )
            # Switch dispatch to TakeOutAction for this invocation. Safe because
            # ``func()`` reads ``self.action`` after ``resolve_action_args()``,
            # and Evennia instantiates commands per invocation.
            self.action = TakeOutAction()
            return {"target": target}
        return {"target": self.search_or_raise(args)}


class CmdDrop(ArxCommand):
    """Drop an item."""

    key = "drop"
    locks = "cmd:all()"
    action = DropAction()

    def resolve_action_args(self) -> dict[str, Any]:
        name = self.require_args("Drop what?")
        return {"target": self.search_or_raise(name, location=self.caller)}


class CmdGive(ArxCommand):
    """Give an item to someone."""

    key = "give"
    locks = "cmd:all()"
    action = GiveAction()

    def resolve_action_args(self) -> dict[str, Any]:
        item_name, recipient_name = self.parse_two_args(
            "to",
            empty_msg="Give what to whom?",
            usage_msg="Usage: give <item> to <recipient>",
        )
        target = self.search_or_raise(item_name, location=self.caller)
        recipient = self.search_or_raise(recipient_name)
        return {"target": target, "recipient": recipient}


class CmdHome(ArxCommand):
    """Return to your home — or set it.

    Usage:
      home        - recall to your home location
      home/set    - make the room you're standing in your home (you must own or rent it)

    Your home is where ``home`` recalls you to; a residence defaults to the first room you
    rent or acquire until you change it here (#1514).
    """

    key = "home"
    aliases: ClassVar[list[str]] = ["recall"]
    locks = "cmd:all()"
    action = HomeAction()

    SET_SWITCH: ClassVar[str] = "set"

    def _execute(self) -> None:
        # ``switches`` is populated by the cmdhandler at parse time; a directly-constructed
        # command (unit tests) may not have it, so default to empty.
        switches = getattr(self, "switches", None) or ()  # noqa: GETATTR_LITERAL
        if self.SET_SWITCH in switches:
            self._set_home()
            return
        super()._execute()

    def _set_home(self) -> None:
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from commands.exceptions import CommandError  # noqa: PLC0415
        from world.locations.services import is_owner, is_tenant, set_residence  # noqa: PLC0415
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        room = self.caller.location
        if room is None:
            msg = "You aren't anywhere you could call home."
            raise CommandError(msg)
        try:
            persona = active_persona_for_sheet(self.caller.sheet_data)
        except (AttributeError, ObjectDoesNotExist):
            persona = None
        if persona is None or not (is_owner(persona, room) or is_tenant(persona, room)):
            msg = "You can only set your home to a room you own or rent."
            raise CommandError(msg)
        set_residence(character=self.caller, room=room)
        self.msg(f"Home set to {room.key}.")
