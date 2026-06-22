"""Telnet ``imbue`` command — finisher for the Rite of Imbuing ceremony.

Grammar: ``imbue thread=<name or id> amount=<n>``

Requires a PendingRitualEffect for 'Rite of Imbuing' (ImbueAction's
prerequisite enforces this). Resolves the thread by name (iexact) or pk.
"""

from __future__ import annotations

from typing import Any

from actions.definitions.imbue import ImbueAction
from commands.command import ArxCommand
from commands.exceptions import CommandError

_THREAD_KWARG = "thread"
_AMOUNT_KWARG = "amount"


class CmdImbue(ArxCommand):
    """Advance a thread's level by spending resonance (finisher for Rite of Imbuing).

    Must have performed ``ritual Rite of Imbuing`` first.

    Syntax:
        ``imbue thread=<name or id> amount=<n>``

    Example:
        ``imbue thread=Ember of Endurance amount=5``
    """

    key = "imbue"
    locks = "cmd:all()"
    action = ImbueAction()

    def resolve_action_args(self) -> dict[str, Any]:
        """Parse ``imbue thread=<name or id> amount=<n>`` into action kwargs."""
        from world.magic.models import Thread  # noqa: PLC0415

        args = self.require_args("Imbue what? (imbue thread=<name or id> amount=<n>)")
        parsed = self._parse_kwargs(args)

        thread_val = parsed.get(_THREAD_KWARG, "").strip()
        if not thread_val:
            msg = "Specify a thread: thread=<name or id>."
            raise CommandError(msg)

        amount_str = parsed.get(_AMOUNT_KWARG, "").strip()
        if not amount_str or not amount_str.isdigit() or int(amount_str) <= 0:
            msg = "Specify a positive amount: amount=<n>."
            raise CommandError(msg)

        sheet = self.caller.sheet_data
        thread = self.resolve_by_name_or_id(
            Thread,
            thread_val,
            not_found_msg=f"No thread found for '{thread_val}'.",
            owner=sheet,
            retired_at__isnull=True,
        )

        return {"thread": thread, "amount": int(amount_str)}

    @staticmethod
    def _parse_kwargs(args: str) -> dict[str, str]:
        """Parse ``key=value`` tokens left to right.

        ``amount`` is a single whitespace-delimited token; once a ``thread=`` token
        is seen, the remainder of the line (up to ``amount=``) is its value, so thread
        names may contain spaces.
        """
        out: dict[str, str] = {}
        tokens = args.split()
        index = 0
        while index < len(tokens):
            token = tokens[index]
            if "=" not in token:
                index += 1
                continue
            key, _, value = token.partition("=")
            if key == _THREAD_KWARG:
                # Greedily consume remaining tokens until we hit ``amount=``
                remaining: list[str] = [value]
                index += 1
                while index < len(tokens):
                    next_token = tokens[index]
                    if next_token.startswith(f"{_AMOUNT_KWARG}="):
                        break
                    remaining.append(next_token)
                    index += 1
                out[_THREAD_KWARG] = " ".join(remaining).strip()
                continue
            out[key] = value
            index += 1
        return out
