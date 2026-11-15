"""Telnet ``resonances`` (#5124): the "Your resonances" panel as lines.

Lists each resonance the character holds, whether it is kindled, how strongly (in the
strength's own word) and why. The same read the web panel makes (``kindled_resonances``);
no numbers and no game logic live here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from commands.command import ArxCommand

if TYPE_CHECKING:
    from world.magic.types.kindling import KindledResonance

NO_SHEET = "You have no character sheet."
NO_RESONANCES = "You hold no resonances."


def kindled_lines(rows: list[KindledResonance]) -> list[str]:
    """One block per resonance: name and affinity, its state, then why it is kindled."""
    lines: list[str] = []
    for row in rows:
        head = f"|w{row.resonance.name}|n ({row.resonance.affinity.name})"
        if row.tier is None:
            lines.append(f"{head} - Not kindled")
            continue
        lines.append(f"{head} - Kindled, {row.tier.name.lower()}")
        lines.extend(f"  {reason}" for reason in row.reasons)
    return lines


class CmdKindledResonances(ArxCommand):
    """See which of your resonances are kindled, how strongly, and why.

    Usage:
        resonances
    """

    key = "resonances"
    locks = "cmd:all()"
    help_category = "Magic"
    action = None

    def func(self) -> None:
        from world.magic.services.kindling import kindled_resonances  # noqa: PLC0415

        sheet = self.caller.character_sheet
        if sheet is None:
            self.msg(NO_SHEET)
            return
        rows = kindled_resonances(sheet)
        if not rows:
            self.msg(NO_RESONANCES)
            return
        self.msg("\n".join(kindled_lines(rows)))
