"""Positions telnet command — the ``position`` namespace (#2005).

Bare ``position`` lists the caller's current room's staged positions with
their occupants and ADJACENT-reach adjacency, or reports the room as
unstaged. ``position <name>`` resolves a Position by name scoped to the
caller's room (telnet has no pk to reference; case-insensitive exact match,
falling back to a unique prefix match, mirroring ``CmdPlaces``) and
dispatches ``TakePositionAction`` when the caller is not yet placed anywhere,
or ``MoveToPositionAction`` when already placed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from actions.definitions.positioning import MoveToPositionAction, TakePositionAction
from commands.command import ArxCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from world.areas.positioning.models import Position


class CmdPosition(ArxCommand):
    """Enter or move within your current room's tactical position graph.

    Usage:
        position
        position <name>
    """

    key = "position"
    locks = "cmd:all()"

    def func(self) -> None:
        raw = (self.args or "").strip()
        if not raw:
            self._list_positions()
            return
        try:
            self._do_position(raw)
        except CommandError as err:
            self.msg(str(err))
            self.msg(command_error={"error": str(err), "command": self.raw_string or ""})

    def _list_positions(self) -> None:
        from world.areas.positioning.models import ObjectPosition, Position  # noqa: PLC0415
        from world.areas.positioning.services import room_position_adjacency  # noqa: PLC0415

        room = self.caller.location
        if room is None:
            self.msg("You aren't anywhere.")
            return
        positions = list(Position.objects.filter(room=room).order_by("pk"))
        if not positions:
            self.msg("This room has no positions staged.")
            return

        name_by_id = {p.pk: p.name for p in positions}
        adjacency = {a.position_id: a.adjacent_position_ids for a in room_position_adjacency(room)}
        occupants_by_position: dict[int, list[str]] = {p.pk: [] for p in positions}
        for obj_pos in ObjectPosition.objects.filter(position__room=room).select_related(
            "objectdb", "position"
        ):
            occupants_by_position.setdefault(obj_pos.position_id, []).append(obj_pos.objectdb.key)

        lines = ["Positions here:"]
        for p in positions:
            occupants = occupants_by_position.get(p.pk, [])
            occupants_text = ", ".join(occupants) if occupants else "empty"
            adjacent_names = [
                name_by_id[pid] for pid in adjacency.get(p.pk, []) if pid in name_by_id
            ]
            adjacent_text = ", ".join(adjacent_names) if adjacent_names else "none"
            lines.append(
                f"  {p.name} ({p.get_kind_display()}) — "
                f"occupants: {occupants_text}; adjacent: {adjacent_text}"
            )
        self.msg("\n".join(lines))

    def _resolve_position(self, room: object, name: str) -> Position:
        from world.areas.positioning.models import Position  # noqa: PLC0415

        positions = list(Position.objects.filter(room=room))
        lname = name.lower()
        for position in positions:
            if position.name.lower() == lname:
                return position
        prefix_matches = [p for p in positions if p.name.lower().startswith(lname)]
        if len(prefix_matches) == 1:
            return prefix_matches[0]
        if len(prefix_matches) > 1:
            names = ", ".join(p.name for p in prefix_matches)
            msg = f"'{name}' is ambiguous: {names}."
            raise CommandError(msg)
        msg = f"No such position here: '{name}'."
        raise CommandError(msg)

    def _do_position(self, name: str) -> None:
        from world.areas.positioning.services import position_of  # noqa: PLC0415

        room = self.caller.location
        if room is None:
            msg = "You aren't anywhere."
            raise CommandError(msg)
        position = self._resolve_position(room, name)

        if position_of(self.caller) is None:
            result = TakePositionAction().run(self.caller, position_id=position.pk)
        else:
            result = MoveToPositionAction().run(self.caller, position_id=position.pk)
        if result.message:
            self.msg(result.message)
