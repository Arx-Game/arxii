"""Telnet face of the retire action (#2287).

Thin command over the REGISTRY ``RetireCharacterAction``: a dead character's
player fires ``retire`` when ready to let go; staff may force-retire another
dead character with ``retire <name>`` (offscreen deaths).
"""

from __future__ import annotations

from typing import Any, ClassVar

from actions.definitions.vitals import RetireCharacterAction
from commands.command import ArxCommand


class CmdRetire(ArxCommand):
    """Lay your dead character to rest.

    Usage:
      retire            - release your own dead character (final; no relogin)
      retire <name>     - (staff) force-retire another dead character
    """

    key = "retire"
    aliases: ClassVar[list[str]] = []
    locks = "cmd:all()"
    help_category = "General"
    action = RetireCharacterAction()

    def resolve_action_args(self) -> dict[str, Any]:
        args = self.args.strip()
        return {"target_name": args} if args else {}
