"""Telnet face of the mundane-stealth stance (#3288): ``sneak`` / ``unsneak``.

Thin over ``SneakAction``/``UnsneakAction`` (``actions/definitions/stealth.py``) —
the same seam the web action dispatch uses. Mirrors ``CmdHide``'s verb-branch
shape (``commands/presence.py``); distinct from it entirely: ``hide`` is OOC
presence privacy, ``sneak`` is IC concealment with mandatory OOC presence
disclosure. No business logic in the command.
"""

from __future__ import annotations

from typing import ClassVar

from actions.definitions.stealth import SneakAction, UnsneakAction
from commands.command import ArxCommand

# The command verb that drops the stance (vs. ``sneak`` which attempts it).
CMD_UNSNEAK = "unsneak"


class CmdSneak(ArxCommand):
    """Slip into the shadows, or step back out of them.

    While sneaking, other characters can't see you — but everyone in the room
    always knows an unseen presence is there, and your arrival in each new room
    is announced anonymously. One attempt per room: fail, and you must move on
    before trying again. Guards contest your stealth when you enter their turf.

    Usage:
      sneak      - attempt to hide (one roll per room)
      unsneak    - step out of the shadows
    """

    key = "sneak"
    aliases: ClassVar[list[str]] = [CMD_UNSNEAK]
    locks = "cmd:all()"
    help_category = "General"
    action = None

    def func(self) -> None:
        action = UnsneakAction() if self.cmdstring == CMD_UNSNEAK else SneakAction()
        result = action.run(actor=self.caller)
        if result.message:
            self.msg(result.message)
