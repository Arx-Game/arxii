"""Telnet ``manageroom`` command (#1470) — the room-editor MVP, owner-gated.

Thin over ``RoomEditAction`` (the same seam the web action-dispatch calls). A room
owner standing in their room edits its name, description, or public/private
listing. No business logic here — ownership gating + the writes live in the action
and ``world.locations.services.set_room_display_data``.
"""

from __future__ import annotations

from typing import Any

from actions.definitions.locations import RoomEditAction
from commands.command import ArxCommand
from commands.exceptions import CommandError

_USAGE = (
    "Usage:\n"
    "  manageroom/name <new name>\n"
    "  manageroom/desc <description>\n"
    "  manageroom/public <yes|no>"
)

_AFFIRMATIVE = frozenset({"yes", "y", "true", "on", "1", "public"})


class CmdManageRoom(ArxCommand):
    """Edit a room you own — its name, description, or public/private listing.

    You must be standing in a room you own.

    Usage:
      manageroom/name <new name>
      manageroom/desc <description>
      manageroom/public <yes|no>
    """

    key = "manageroom"
    locks = "cmd:all()"
    help_category = "Building"
    action = RoomEditAction()

    def resolve_action_args(self) -> dict[str, Any]:
        switches = set(self.switches or [])
        args = (self.args or "").strip()
        if "name" in switches:  # noqa: STRING_LITERAL — Evennia switch name, not a discriminator
            if not args:
                msg = "Give the new room name."
                raise CommandError(msg)
            return {"name": args}
        if switches & {"desc", "description"}:  # noqa: STRING_LITERAL — Evennia switch names
            if not args:
                msg = "Give the new description."
                raise CommandError(msg)
            return {"description": args}
        if "public" in switches:  # noqa: STRING_LITERAL — Evennia switch name
            if not args:
                msg = "Use 'manageroom/public <yes|no>'."
                raise CommandError(msg)
            return {"is_public": args.lower() in _AFFIRMATIVE}
        raise CommandError(_USAGE)
