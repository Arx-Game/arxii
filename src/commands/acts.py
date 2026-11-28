"""Telnet ``acts`` (#5327): the acts a character can point a mark at, as numbered lines.

Lists the character's newest 20 unmarked acts, each behind its own id, with its age and what
situations suggested for it, the same read the web "Pointing at" list makes
(``pointable_acts_page``). ``pose/reach <resonance>:<id>=<text>`` marks the act with that id; an
id never shifts when a newer act lands. No game logic lives here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils import timezone
from django.utils.timesince import timesince

from commands.command import ArxCommand

if TYPE_CHECKING:
    from world.magic.models import RecordedAct

NO_SHEET = "You have no character sheet."
NO_ACTS = "You have no acts to mark. Take an action and it will be listed here."
HEADER = "Your acts you have not marked:"
FOOTER = "Mark one with: pose/reach <resonance>:<act number>=<text>"
SHOWN_ACTS = 20
MORE_ACTS = "  And {count} older {noun} not shown."
NO_SUGGESTION = "No resonance suggested."
JUST_NOW = "just now"


def _age(act: RecordedAct) -> str:
    """How long ago the act happened: "2 minutes ago", or "just now" within the first minute."""
    # Django joins the number and its unit with a no-break space; a terminal wants a plain one.
    since = timesince(act.created_at, timezone.now(), depth=1).replace("\u00a0", " ")
    return JUST_NOW if since.startswith("0 ") else f"{since} ago"


def act_lines(acts: list[RecordedAct], older: int = 0) -> list[str]:
    """The lines for ``acts``: each act's own id, label and age, then each suggestion (a
    resonance and the reason a situation gave) or the line saying none was suggested, and how
    many older acts the list leaves out."""
    lines = [HEADER]
    for act in acts:
        lines.append(f"  {act.pk}. {act.label} ({_age(act)})")
        suggestions = act.cached_suggestions
        if not suggestions:
            lines.append(f"     {NO_SUGGESTION}")
        lines.extend(
            f"     {row.resonance.name}: {row.reason}"
            if row.reason
            else f"     {row.resonance.name}"
            for row in suggestions
        )
    if older:
        lines.append(MORE_ACTS.format(count=older, noun="act is" if older == 1 else "acts are"))
    lines.append(FOOTER)
    return lines


class CmdActs(ArxCommand):
    """List the acts you can mark with a resonance.

    Usage:
        acts

    Shows what your character did that you have not marked, newest first, with the
    resonance a situation suggested for each. Mark one by the number printed before it with
    ``pose/reach <resonance>:<act number>=<text>``.
    """

    key = "acts"
    locks = "cmd:all()"
    help_category = "Magic"
    action = None

    def func(self) -> None:
        from world.magic.services.marking import pointable_acts_page  # noqa: PLC0415

        sheet = self.caller.character_sheet
        if sheet is None:
            self.msg(NO_SHEET)
            return
        acts, older = pointable_acts_page(sheet, SHOWN_ACTS)
        if not acts:
            self.msg(NO_ACTS)
            return
        self.msg("\n".join(act_lines(acts, older)))
