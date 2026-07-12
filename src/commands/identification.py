"""Telnet face of ``IdentifyAction`` (#1107 slice 5).

A bare ``ArxCommand`` delegate, mirroring ``CmdSearch`` (``commands/investigation.py``) /
``CmdSteal`` (``commands/currency.py``) — parse text, hand kwargs to ``action.run()``, message
the result to the caller only. No consent flow: identifying someone is a private perception
roll about the viewer's own understanding, not something that acts on the target's behavior
(ADR-0024, "consent gates behavior, not benefit") — unlike Deceive/Persuade/Flirt, which ride
``ConsentRequestCommand`` (``commands/consent.py``).
"""

from __future__ import annotations

from typing import Any

from actions.definitions.identification import IdentifyAction
from commands.command import ArxCommand
from commands.exceptions import CommandError

_DEFAULT_LOCKS = "cmd:all()"
_IDENTIFY_WHOM = "Identify whom?"


class CmdIdentify(ArxCommand):
    """Try to see through a mask or disguise to who's really underneath.

    Usage:
      identify <target>
      identify <target>=<guess>

    The optional ``=<guess>`` names who you think is really underneath — a correct
    guess eases the check; a wrong one is just a failure, same as no guess at all.
    """

    key = "identify"
    locks = _DEFAULT_LOCKS
    help_category = "General"
    action = IdentifyAction()

    def resolve_action_args(self) -> dict[str, Any]:
        args = self.require_args(_IDENTIFY_WHOM)
        target_name, _sep, guess = args.partition("=")
        target_name = target_name.strip()
        if not target_name:
            raise CommandError(_IDENTIFY_WHOM)
        target = self.search_or_raise(target_name)

        kwargs: dict[str, Any] = {"target": target}
        guess = guess.strip()
        if guess:
            kwargs["guess"] = guess
        return kwargs
