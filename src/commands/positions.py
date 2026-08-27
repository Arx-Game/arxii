"""Positions telnet command — the ``position`` namespace (#2005, #3385).

Bare ``position`` lists the caller's current room's staged positions with
their occupants and ADJACENT-reach adjacency, or reports the room as
unstaged. ``position <name>`` resolves a Position by name scoped to the
caller's room (telnet has no pk to reference; case-insensitive exact match,
falling back to a unique prefix match, mirroring ``CmdPlaces``) and
dispatches ``TakePositionAction`` when the caller is not yet placed anywhere,
or ``MoveToPositionAction`` when already placed.

``position/place <target>=<position name>`` (#3385) dispatches
``GMPlaceInPositionAction`` -- staff/GM-fiat unchecked placement of any
co-located object. No business logic here: the command resolves ``<target>``
via a co-located search and ``<position name>`` via the shared
``resolve_position_by_name`` helper, then hands both to the action, which
re-checks the GM gate and co-location server-side regardless of what this
command validated.
"""

from __future__ import annotations

from actions.definitions.positioning import (
    GMPlaceInPositionAction,
    MoveToPositionAction,
    TakePositionAction,
)
from commands.command import ArxCommand
from commands.exceptions import CommandError
from commands.utils.gm_resolution import resolve_position_by_name

_SWITCH_PLACE = "place"
_USAGE_PLACE = "Usage: position/place <target>=<position name>"


class CmdPosition(ArxCommand):
    """Enter or move within your current room's tactical position graph.

    Usage:
        position
        position <name>
        position/place <target>=<position name>
    """

    key = "position"
    locks = "cmd:all()"

    def func(self) -> None:
        # Suppression justified: Evennia cmdhandler sets .switches at parse time; hand-built
        # test instances that call func() directly never set it.
        raw_switches = getattr(self, "switches", None) or []  # noqa: GETATTR_LITERAL
        switches = {s.lower() for s in raw_switches}
        if _SWITCH_PLACE in switches:
            try:
                self._do_place()
            except CommandError as err:
                self.msg(str(err))
            return

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

    def _do_position(self, name: str) -> None:
        from world.areas.positioning.services import position_of  # noqa: PLC0415

        room = self.caller.location
        if room is None:
            msg = "You aren't anywhere."
            raise CommandError(msg)
        position = resolve_position_by_name(room, name)

        if position_of(self.caller) is None:
            result = TakePositionAction().run(self.caller, position_id=position.pk)
        else:
            result = MoveToPositionAction().run(self.caller, position_id=position.pk)
        if result.message:
            self.msg(result.message)

    def _do_place(self) -> None:
        args = (self.args or "").strip()
        target_part, sep, position_part = args.partition("=")
        target_name = target_part.strip()
        position_name = position_part.strip()
        if not sep or not target_name or not position_name:
            raise CommandError(_USAGE_PLACE)

        room = self.caller.location
        if room is None:
            msg = "You aren't anywhere."
            raise CommandError(msg)

        # Co-located search only -- cannot name anything outside the caller's
        # own room. GMPlaceInPositionAction re-validates co-location regardless.
        target = self.caller.search(target_name, location=room)
        if target is None:
            return  # search() sends its own error message

        position = resolve_position_by_name(room, position_name)

        result = GMPlaceInPositionAction().run(
            self.caller, position_id=position.pk, target_object_id=target.pk
        )
        if result.message:
            self.msg(result.message)
