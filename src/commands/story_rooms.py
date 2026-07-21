"""Telnet faces of the story-room play verbs (#2450).

Thin commands over the four registry actions in
``actions/definitions/story_builder.py``: ``SpinUpSceneRoomAction`` /
``CloseSceneRoomAction`` (GM lifecycle, gated by
``MinimumGMLevelPrerequisite`` inside the action) and
``JoinStoryRoomAction`` / ``LeaveStoryRoomAction`` (open to any character
with a sheet — authorization is the grant itself, checked inside the
service). Locks are ``cmd:all()`` throughout; real authorization lives in
the actions/services, the same seam ``setstage.py`` uses.
"""

from __future__ import annotations

from typing import Any

from actions.definitions.story_builder import (
    CloseSceneRoomAction,
    JoinStoryRoomAction,
    LeaveStoryRoomAction,
    SpinUpSceneRoomAction,
)
from commands.command import ArxCommand
from commands.exceptions import CommandError
from world.gm.models import StoryRoomGrant

# Shared lock string for story-room commands (authorization lives in the actions).
_ALL_LOCK = "cmd:all()"

_CLOSE_SUBVERB = "close"
_SCENEROOM_USAGE = "Usage: sceneroom <name> = <description> | sceneroom close <#room-id>"


class CmdSceneRoom(ArxCommand):
    """Spin up or close a temporary GM-owned scene room.

    Usage:
      sceneroom <name> = <description>   -- spin up a new scene room
      sceneroom close <#room-id>         -- close a scene room you own

    The word "close" is reserved as the first token: a room literally named
    "close" must still be created with the ``=`` form (``sceneroom close =
    <description>``), since the presence of ``=`` is what routes to
    spin-up rather than close.
    """

    key = "sceneroom"
    locks = _ALL_LOCK
    help_category = "Building"

    def func(self) -> None:
        """Route to spin-up or close; surface ``CommandError`` as a player message."""
        try:
            self._execute()
        except CommandError as err:
            self.msg(str(err))
            self.msg(command_error={"error": str(err), "command": self.raw_string or ""})

    def _execute(self) -> None:
        raw = (self.args or "").strip()
        if not raw:
            raise CommandError(_SCENEROOM_USAGE)
        if "=" in raw:
            self._do_spin_up(raw)
            return
        parts = raw.split(maxsplit=1)
        if parts[0].lower() == _CLOSE_SUBVERB:
            rest = parts[1].strip() if len(parts) > 1 else ""
            self._do_close(rest)
            return
        raise CommandError(_SCENEROOM_USAGE)

    def _do_spin_up(self, raw: str) -> None:
        name, _, description = raw.partition("=")
        name = name.strip()
        description = description.strip()
        if not name:
            raise CommandError(_SCENEROOM_USAGE)
        result = SpinUpSceneRoomAction().run(actor=self.caller, name=name, description=description)
        if result.message:
            self.msg(result.message)

    def _do_close(self, rest: str) -> None:
        room_id_raw = rest.strip().lstrip("#")
        if not room_id_raw.isdigit():
            raise CommandError(_SCENEROOM_USAGE)
        result = CloseSceneRoomAction().run(actor=self.caller, room_id=int(room_id_raw))
        if result.message:
            self.msg(result.message)


class CmdJoinRoom(ArxCommand):
    """Join a story or temp scene room you've been granted access to.

    Usage:
      joinroom               -- list rooms you may join
      joinroom <#id|name>    -- join one (name matches your own grants only)

    If several of your granted rooms share a name, the lowest-id one is
    picked -- join by #id to disambiguate.
    """

    key = "joinroom"
    locks = _ALL_LOCK
    help_category = "Building"
    action = JoinStoryRoomAction()

    def resolve_action_args(self) -> dict[str, Any]:
        raw = (self.args or "").strip()
        grants = self._own_grants()
        room_id_raw = raw.lstrip("#")
        if room_id_raw.isdigit():
            return {"room_id": int(room_id_raw)}
        grant = grants.filter(room__objectdb__db_key__iexact=raw).order_by("room_id").first()
        if grant is None:
            msg = "No such room among your grants. (joinroom to see them.)"
            raise CommandError(msg)
        return {"room_id": grant.room.objectdb_id}

    def func(self) -> None:
        raw = (self.args or "").strip()
        if not raw:
            try:
                self._list_grants()
            except CommandError as err:
                self.msg(str(err))
                self.msg(command_error={"error": str(err), "command": self.raw_string or ""})
            return
        super().func()

    def _own_grants(self) -> Any:
        sheet = self.caller.character_sheet
        if sheet is None:
            msg = "You have no character sheet."
            raise CommandError(msg)
        return StoryRoomGrant.objects.filter(character=sheet).select_related("room__objectdb")

    def _list_grants(self) -> None:
        grants = list(self._own_grants())
        if not grants:
            self.msg("You have no story room grants.")
            return
        lines = ["Rooms you may join:"]
        lines += [f"  #{g.room.objectdb_id} {g.room.objectdb.db_key}" for g in grants]
        self.msg("\n".join(lines))


class CmdLeaveRoom(ArxCommand):
    """Leave the story room you're currently in, returning to where you joined from.

    Usage:
      leaveroom
    """

    key = "leaveroom"
    locks = _ALL_LOCK
    help_category = "Building"
    action = LeaveStoryRoomAction()
