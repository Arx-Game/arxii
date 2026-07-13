"""Telnet face of the wake action (#2287).

Thin command: parses no args and delegates directly to the REGISTRY
``WakeAction`` so an unconscious telnet player can attempt to wake (one
check per round-equivalent; guaranteed past the config deadline).
"""

from __future__ import annotations

from typing import ClassVar

from actions.definitions.vitals import WakeAction
from commands.command import ArxCommand


class CmdWake(ArxCommand):
    """Attempt to wake from unconsciousness.

    Usage:
      wake

    One attempt per round; waking gets easier the longer you are out and
    as you are healed.
    """

    key = "wake"
    aliases: ClassVar[list[str]] = []
    locks = "cmd:all()"
    help_category = "General"
    action = WakeAction()
