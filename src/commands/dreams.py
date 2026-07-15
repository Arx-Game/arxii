"""Telnet face of the sleep action (#2290).

Thin command: parses no args and delegates directly to the REGISTRY
``SleepAction`` so a player can voluntarily sleep to enter the dream realm.
"""

from __future__ import annotations

from typing import ClassVar

from actions.definitions.dreams import SleepAction
from commands.command import ArxCommand


class CmdSleep(ArxCommand):
    """Voluntarily sleep to enter the dream realm.

    Usage:
      sleep

    While asleep, your perception shifts to the dream layer. Use ``wake``
    to return to the waking world (unless dream-engaged in combat or an event).
    """

    key = "sleep"
    aliases: ClassVar[list[str]] = []
    locks = "cmd:all()"
    help_category = "General"
    action = SleepAction()
