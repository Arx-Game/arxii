"""Telnet ``resonances`` (#5124): the "Your resonances" panel as lines.

Lists each resonance the character holds, whether it is kindled, how strongly (in the
strength's own word) and why. The same read the web panel makes (``kindled_resonances_now``);
no numbers and no game logic live here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from commands.command import ArxCommand

if TYPE_CHECKING:
    from collections.abc import Mapping

    from world.magic.services.impulses import Impulse
    from world.magic.types.kindling import KindledResonance

NO_SHEET = "You have no character sheet."
NO_RESONANCES = "You hold no resonances."


def kindled_lines(
    rows: list[KindledResonance], waiting: Mapping[int, int] | None = None
) -> list[str]:
    """One block per resonance: name and affinity, its state, then why it is kindled. A
    resonance whose days have piled up a trickle (``waiting``, resonance id to amount) says
    how much waits for the next anima ritual (#5308), as the web panel does."""
    lines: list[str] = []
    for row in rows:
        head = f"|w{row.resonance.name}|n ({row.resonance.affinity.name})"
        if row.tier is None:
            lines.append(f"{head} - Not kindled")
        else:
            lines.append(f"{head} - Kindled, {row.tier.name.lower()}")
            lines.extend(f"  {reason}" for reason in row.reasons)
        trickle = waiting.get(row.resonance.pk, 0) if waiting else 0
        if trickle > 0:
            lines.append(f"  {trickle} waiting for your anima ritual")
    return lines


def impulse_lines(impulses: list[Impulse]) -> list[str]:
    """The Impulses section: the pull of corruption the character carries (#5177). Each
    impulse names its resonance, says whether something it cares about is here, and shows the
    words staff wrote for it while it is."""
    lines = ["|wImpulses|n"]
    for impulse in impulses:
        state = "here now" if impulse.present else "not here"
        lines.append(f"{impulse.label} - {state}")
        if impulse.present:
            lines.extend(f"  {reason}" for reason in impulse.reasons)
            if impulse.text:
                lines.append(f"  {impulse.text}")
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
        from world.magic.services.gain import waiting_trickles  # noqa: PLC0415
        from world.magic.services.impulses import (  # noqa: PLC0415
            safe_refresh_impulses_for_character,
        )
        from world.magic.services.kindling import kindled_resonances_now  # noqa: PLC0415

        sheet = self.caller.character_sheet
        if sheet is None:
            self.msg(NO_SHEET)
            return
        rows = kindled_resonances_now(sheet)
        refreshed = safe_refresh_impulses_for_character(self.caller)
        impulses = list(refreshed.impulses) if refreshed is not None else []
        if not rows and not impulses:
            self.msg(NO_RESONANCES)
            return
        lines = kindled_lines(rows, waiting_trickles(sheet)) if rows else [NO_RESONANCES]
        if impulses:
            lines = [*lines, "", *impulse_lines(impulses)]
        self.msg("\n".join(lines))
