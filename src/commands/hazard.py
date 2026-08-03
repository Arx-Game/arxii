"""Telnet answers to the hazard prompt (#2846 gap close).

The hazard prompt has always told players they may flee or tough it out, but
until now only the web client could act on it — the two actions had no telnet
verb at all, so a burning vampire on telnet was reading an instruction they
could not follow. These are the missing verbs:

- ``endure`` — stand your ground and take what the hazard deals (suppresses
  re-prompting and the AFK auto-flee for a window).
- ``retreat`` — take the auto-flee pathing consciously, right now.

Covering up and moving to shade were always available (``wear``, movement);
they clear the hazard by clearing the exposure rather than by answering the
prompt.
"""

from __future__ import annotations

from typing import ClassVar

from actions.definitions.hazards import HazardEndureAction, HazardRetreatAction
from commands.command import ArxCommand


class CmdEndure(ArxCommand):
    """Stand your ground against a hazard that is harming you.

    Usage:
      endure

    You stay exactly where you are and take what comes. Your instincts stop
    dragging you to safety for a while, which is the point, and the risk.
    """

    key = "endure"
    aliases: ClassVar[list[str]] = ["toughitout"]
    locks = "cmd:all()"
    help_category = "General"
    action = HazardEndureAction()


class CmdRetreat(ArxCommand):
    """Retreat from a hazard to the nearest shelter.

    Usage:
      retreat

    The same pathing your instincts would use if you froze, taken
    deliberately, and immediately.
    """

    key = "retreat"
    aliases: ClassVar[list[str]] = []
    locks = "cmd:all()"
    help_category = "General"
    action = HazardRetreatAction()
