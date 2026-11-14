"""Telnet ``imbue`` command — finisher for the Rite of Imbuing ceremony.

Grammar: ``imbue thread=<name or id> amount=<n> [resonance=<name>]``

    A thread is named by its own name or its anchor's (a Gift thread by the Gift's name);
    ``threads`` lists the names.

``resonance=`` names the resonance that pays; left out, the thread's leading resonance
pays (#5123). It must be one the character holds.

Requires a PendingRitualEffect for 'Rite of Imbuing' (ImbueAction's
prerequisite enforces this). Resolves the thread by name (iexact) or pk.
"""

from __future__ import annotations

from typing import Any

from actions.definitions.imbue import ImbueAction
from commands.command import ArxCommand
from commands.exceptions import CommandError
from commands.utils.held_resonance import held_resonance
from commands.utils.thread_lookup import resolve_thread

_THREAD_KWARG = "thread"
_AMOUNT_KWARG = "amount"
_RESONANCE_KWARG = "resonance"
_KEYS = (_THREAD_KWARG, _AMOUNT_KWARG, _RESONANCE_KWARG)
_MULTIWORD_KEYS = (_THREAD_KWARG, _RESONANCE_KWARG)


class CmdImbue(ArxCommand):
    """Advance a thread's level by spending resonance (finisher for Rite of Imbuing).

    Must have performed ``ritual Rite of Imbuing`` first.

    Syntax:
        ``imbue thread=<name or id> amount=<n> [resonance=<name>]``

    Example:
        ``imbue thread=Ember of Endurance amount=5 resonance=Domination``
    """

    key = "imbue"
    locks = "cmd:all()"
    action = ImbueAction()

    def resolve_action_args(self) -> dict[str, Any]:
        """Parse ``imbue thread=<name or id> amount=<n>`` into action kwargs."""
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
        thread = resolve_thread(
            sheet, thread_val, not_found_msg=f"No thread found for '{thread_val}'."
        )

        kwargs: dict[str, Any] = {"thread": thread, "amount": int(amount_str)}
        resonance_val = parsed.get(_RESONANCE_KWARG, "").strip()
        if _RESONANCE_KWARG in parsed:
            kwargs["resonance_id"] = held_resonance(sheet, resonance_val).pk
        return kwargs

    @staticmethod
    def _parse_kwargs(args: str) -> dict[str, str]:
        """Parse ``key=value`` tokens left to right.

        ``amount`` is a single whitespace-delimited token (a stray word after it is
        ignored). ``thread`` and ``resonance`` run on across spaces until the next
        ``thread=``, ``amount=`` or ``resonance=`` token, so either may have a name of
        several words.
        """
        out: dict[str, str] = {}
        key: str | None = None
        words: list[str] = []
        for token in args.split():
            head, sep, value = token.partition("=")
            head = head.lower()
            if sep and head in _KEYS:
                if key is not None:
                    out[key] = " ".join(words).strip()
                key, words = head, [value]
                if key == _AMOUNT_KWARG:
                    out[key], key = value, None
            elif key in _MULTIWORD_KEYS:
                words.append(token)
            elif sep:
                out[head] = value
        if key is not None:
            out[key] = " ".join(words).strip()
        return out
