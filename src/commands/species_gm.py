"""Telnet face of the GM species-condition grants (#2862 gap close)."""

from __future__ import annotations

from typing import Any, ClassVar

from actions.definitions.species_gm import ApplyShadeUndeathAction
from commands.command import ArxCommand


class CmdMakeShade(ArxCommand):
    """Make a character a Shade (GM tool).

    Usage:
      makeshade <character>

    Grants the undead condition and its economy anchor: no natural anima
    recovery, a daily leak, and the ability to drain essence from others.
    """

    key = "makeshade"
    aliases: ClassVar[list[str]] = []
    locks = "cmd:all()"
    help_category = "GM"
    action = ApplyShadeUndeathAction()

    def resolve_action_args(self) -> dict[str, Any]:
        return {"target_name": self.args.strip()}
