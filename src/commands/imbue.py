"""Telnet ``imbue`` command — finisher for the Rite of Imbuing ceremony.

Grammar: ``imbue thread=<name or id> amount=<n> [resonance=<name>]``

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

_THREAD_KWARG = "thread"
_AMOUNT_KWARG = "amount"
_RESONANCE_KWARG = "resonance"
_KEYS = (_THREAD_KWARG, _AMOUNT_KWARG, _RESONANCE_KWARG)


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

        kwargs: dict[str, Any] = {"thread": thread, "amount": int(amount_str)}
        resonance_val = parsed.get(_RESONANCE_KWARG, "").strip()
        if _RESONANCE_KWARG in parsed:
            kwargs["resonance_id"] = self._held_resonance_id(sheet, resonance_val)
        return kwargs

    @staticmethod
    def _held_resonance_id(sheet: Any, typed: str) -> int:
        """The id of the resonance the character holds under ``typed`` (any case)."""
        from world.magic.models import CharacterResonance  # noqa: PLC0415

        if not typed:
            msg = "Name the resonance that pays: resonance=<name>."
            raise CommandError(msg)
        row = CharacterResonance.objects.filter(
            character_sheet=sheet, resonance__name__iexact=typed
        ).first()
        if row is None:
            held = sorted(
                CharacterResonance.objects.filter(character_sheet=sheet).values_list(
                    "resonance__name", flat=True
                )
            )
            suffix = f" Your resonances: {', '.join(held)}." if held else ""
            msg = f"You hold no resonance called '{typed}'.{suffix}"
            raise CommandError(msg)
        return row.resonance_id

    @staticmethod
    def _parse_kwargs(args: str) -> dict[str, str]:
        """Parse ``key=value`` tokens left to right.

        A value runs on, across spaces, until the next ``thread=``, ``amount=`` or
        ``resonance=`` token, so a thread or a resonance may have a name of several words.
        """
        out: dict[str, str] = {}
        key: str | None = None
        words: list[str] = []
        for token in args.split():
            head, sep, value = token.partition("=")
            if sep and head.lower() in _KEYS:
                if key is not None:
                    out[key] = " ".join(words).strip()
                key, words = head.lower(), [value]
            elif key is not None:
                words.append(token)
        if key is not None:
            out[key] = " ".join(words).strip()
        return out
