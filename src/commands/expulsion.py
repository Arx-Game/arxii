"""Telnet command for the unresistable expulsion valve (#2989).

    expel <character>       - show a disruptive character out and bar re-entry
    expel/lift <character>  - lift an active bar in this room

Owner-gated (``IsRoomOwnerPrerequisite``). Not a check, not a fight — the
ratified #2989 amendments make this an OOC soft gate the target cannot
resist, regardless of their character's power.
"""

from __future__ import annotations

from commands.command import ArxCommand


class CmdExpel(ArxCommand):
    """Show a disruptive character out of the room, unresistable.

    Usage:
        expel <character>
        expel/lift <character>

    Only the room owner may expel or lift a bar.
    """

    key = "expel"
    locks = "cmd:all()"
    help_category = "Building"
    action = None  # routes to multiple actions

    def func(self) -> None:
        switches = {s.lower() for s in (self.switches or [])}
        args = (self.args or "").strip()

        if not args:
            self.msg("Usage: expel <character> | expel/lift <character>")
            return

        if "lift" in switches:  # noqa: STRING_LITERAL — Evennia switch name
            self._lift(args)
            return

        self._expel(args)

    def _expel(self, name: str) -> None:
        from actions.registry import get_action  # noqa: PLC0415

        target = self.caller.search(name)
        if target is None:
            return

        action = get_action("expel_character")
        result = action.run(self.caller, target=target)
        self.msg(result.message)

    def _lift(self, name: str) -> None:
        from actions.registry import get_action  # noqa: PLC0415

        action = get_action("lift_expulsion_bar")
        result = action.run(self.caller, name=name)
        self.msg(result.message)
