"""Telnet face of the body-carry actions (#2852).

Thin commands delegating to ``CarryBodyAction`` / ``SetDownBodyAction`` —
picking up a downed character (consent-gated for PCs) and setting them down.
"""

from __future__ import annotations

from typing import Any, ClassVar

from actions.definitions.vitals import CarryBodyAction, SetDownBodyAction
from commands.command import ArxCommand


class CmdCarry(ArxCommand):
    """Pick up and carry an unconscious character.

    Usage:
      carry <name>

    The target must be here and out cold (or dead). Player characters must
    have consented to body handling. While you carry them, they come with
    you when you move; use ``setdown`` to put them down.
    """

    key = "carry"
    aliases: ClassVar[list[str]] = []
    locks = "cmd:all()"
    help_category = "General"
    action = CarryBodyAction()

    def resolve_action_args(self) -> dict[str, Any]:
        return {"target_name": self.args.strip()}


class CmdSetDown(ArxCommand):
    """Set down the body you are carrying.

    Usage:
      setdown
    """

    key = "setdown"
    aliases: ClassVar[list[str]] = []
    locks = "cmd:all()"
    help_category = "General"
    action = SetDownBodyAction()
