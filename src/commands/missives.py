"""Telnet face of IC missives (#3289): parsing only, every rule lives in the actions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from commands.command import ArxCommand
from world.currency.constants import parse_coppers

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet

SEND_USAGE = "Usage: missive/send <name>[+coin <amount>][+item <item>]=<message>"
REPLY_USAGE = "Usage: missive/reply <id>[+coin <amount>][+item <item>]=<message>"
_PREVIEW_LENGTH = 40
_EXTRA_COIN = "coin"
_EXTRA_ITEM = "item"
_SWITCH_LIST = "list"
_SWITCH_SEND = "send"
_SWITCH_REPLY = "reply"
_SWITCH_READ = "read"
_SWITCH_ACCEPT = "accept"
_SWITCH_REFUSE = "refuse"


def _parse_extras(parts: list[str]) -> dict[str, Any] | None:
    """``coin <amount>`` and ``item <name>`` pieces after a ``+``; None when one is malformed.

    The amount is written as ``give`` and ``withdraw coins`` take it (``5s``, ``3g 2s``,
    ``40c``), parsed to coppers by the same ``parse_coppers``.
    """
    kwargs: dict[str, Any] = {}
    item_names: list[str] = []
    for part in parts:
        word, _, rest = part.strip().partition(" ")
        rest = rest.strip()
        if not rest:
            return None
        if word.lower() == _EXTRA_COIN:
            coppers = parse_coppers(rest)
            if coppers is None:
                return None
            kwargs["coin_amount"] = coppers
        elif word.lower() == _EXTRA_ITEM:
            item_names.append(rest)
        else:
            return None
    if item_names:
        kwargs["item_names"] = item_names
    return kwargs


def _split_letter(raw: str) -> tuple[str, dict[str, Any], str] | None:
    """``<head>[+coin n][+item x]...=<body>`` into (head, extras, body); None if malformed."""
    left, sep, body = raw.partition("=")
    if not sep or not body.strip():
        return None
    head, *rest = left.split("+")
    if not head.strip():
        return None
    extras = _parse_extras(rest)
    if extras is None:
        return None
    return head.strip(), extras, body.strip()


class CmdMissive(ArxCommand):
    """Write, read and answer missives: letters carried to another persona.

    Usage:
        missive                                   - your missives, newest first
        missive/list                              - the same
        missive/read <id>                         - read one
        missive/send <name>[+coin <amount>][+item <item>]...=<message>
        missive/reply <id>[+coin <amount>][+item <item>]...=<message>
        missive/accept <id>                       - take what came with it
        missive/refuse <id>                       - send what came with it back

    A missive goes out under the face you are wearing, and a reply under the face the
    letter was written to. A * marks one you have not read. Coin is written as
    for give, e.g. +coin 5s or +coin 3g 2s.
    """

    key = "missive"
    takes_switches = True
    locks = "cmd:all()"
    help_category = "Social"
    action = None

    def func(self) -> None:
        from actions.definitions.missives import (  # noqa: PLC0415
            AcceptMissiveAction,
            ReadMissiveAction,
            RefuseMissiveAction,
            ReplyMissiveAction,
            SendMissiveAction,
        )

        switches = [switch.lower() for switch in self.switches]
        switch = switches[0] if switches else _SWITCH_LIST
        raw = (self.args or "").strip()
        simple = {
            _SWITCH_READ: ReadMissiveAction,
            _SWITCH_ACCEPT: AcceptMissiveAction,
            _SWITCH_REFUSE: RefuseMissiveAction,
        }
        if switch == _SWITCH_LIST:
            self.msg(self._render_list())
            return
        if switch in simple:
            if not raw:
                self.msg(f"Usage: missive/{switch} <id>")
                return
            result = simple[switch]().run(actor=self.caller, missive_id=raw)
            self.msg(result.message)
            return
        if switch in (_SWITCH_SEND, _SWITCH_REPLY):
            parsed = _split_letter(raw)
            if parsed is None:
                self.msg(SEND_USAGE if switch == _SWITCH_SEND else REPLY_USAGE)
                return
            head, extras, body = parsed
            if switch == _SWITCH_SEND:
                result = SendMissiveAction().run(
                    actor=self.caller, recipient_name=head, body=body, **extras
                )
            else:
                result = ReplyMissiveAction().run(
                    actor=self.caller, missive_id=head, body=body, **extras
                )
            self.msg(result.message)
            return
        self.msg("Usage: missive[/list|/read|/send|/reply|/accept|/refuse]")

    def _render_list(self) -> str:
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        try:
            sheet = self.caller.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            sheet = None
        if sheet is None:
            return "No active character."
        return _render_missives(sheet)


def _render_missives(sheet: CharacterSheet) -> str:
    """One line per visible missive, newest first: ``* #12 From Ada - Come at once...``."""
    from world.messengers.display import (  # noqa: PLC0415
        display_map_for,
        missive_correspondents,
    )
    from world.messengers.services import sent_by, visible_missives_for  # noqa: PLC0415

    missives = list(visible_missives_for(sheet).order_by("-sent_at", "-pk"))
    if not missives:
        return "You have no missives."
    names = display_map_for(sheet, missives)
    lines = ["|wMissives|n"]
    for missive in missives:
        from_name, to_name = missive_correspondents(sheet, missive, names)
        if sent_by(sheet, missive):
            who = f"To {to_name}"
            mark = " "
        else:
            who = f"From {from_name}"
            mark = "*" if missive.read_at is None else " "
        preview = " ".join(missive.body.split())[:_PREVIEW_LENGTH]
        lines.append(f"{mark} #{missive.pk} {who} - {preview}")
    return "\n".join(lines)
