"""Telnet faces of prayer and the GM-sent vision (#3779).

Thin: parsing only, every rule lives in the actions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from commands.command import ArxCommand

if TYPE_CHECKING:
    from world.worship.types import InvocationOption

_SWITCH_REVEAL = "reveal"
_SWITCH_PRAYER = "prayer"


class CmdPray(ArxCommand):
    """Pray to a being in your own words.

    Usage:
        pray <being>=<your words>

    A prayer is a message, not a mechanic: staff read them, and a god may
    answer one with a vision. Praying at a shrine or temple of the being once a
    week counts as an act of devotion; praying in dire straits may be answered
    at once.
    """

    key = "pray"
    locks = "cmd:all()"
    help_category = "Social"
    action = None

    def func(self) -> None:
        from actions.definitions.worship import PrayAction  # noqa: PLC0415

        raw = (self.args or "").strip()
        if "=" not in raw:
            self.msg("Usage: pray <being>=<your words>")
            return
        being_name, text = (part.strip() for part in raw.split("=", 1))
        if not being_name or not text:
            self.msg("Usage: pray <being>=<your words>")
            return
        result = PrayAction().run(actor=self.caller, being_name=being_name, text=text)
        if result.message:
            self.msg(result.message)


class CmdVision(ArxCommand):
    """Send a character a vision from a being (staff).

    Usage:
        vision[/reveal] <character>/<being>=<prose>
        vision/prayer <id> <character>/<being>=<prose>

    /reveal tells the recipient which being sent it. /prayer <id> marks the
    prayer this answers. A Codex clue or an episode is attached from the web
    dialog; the telnet face carries only the prose.
    """

    key = "vision"
    takes_switches = True
    locks = "cmd:perm(Admin)"
    help_category = "GM"
    action = None

    def func(self) -> None:
        from actions.definitions.worship import SendVisionAction  # noqa: PLC0415

        raw = (self.args or "").strip()
        switches = {switch.lower() for switch in self.switches}
        prayer_id: int | None = None
        if _SWITCH_PRAYER in switches:
            head, _, raw = raw.partition(" ")
            try:
                prayer_id = int(head)
            except ValueError:
                self.msg("Usage: vision/prayer <id> <character>/<being>=<prose>")
                return
            raw = raw.strip()
        if "=" not in raw or "/" not in raw.split("=", 1)[0]:
            self.msg("Usage: vision[/reveal] <character>/<being>=<prose>")
            return
        target, body = (part.strip() for part in raw.split("=", 1))
        recipient_name, being_name = (part.strip() for part in target.split("/", 1))
        result = SendVisionAction().run(
            actor=self.caller,
            account=self.account,
            recipient_name=recipient_name,
            being_name=being_name,
            body=body,
            reveal_source=_SWITCH_REVEAL in switches,
            prayer=prayer_id,
        )
        if result.message:
            self.msg(result.message)


class CmdInvoke(ArxCommand):
    """See which beings you can call on for a check, and how hard it is.

    Usage:
        invoke
        invoke <being>

    Calling on a being's favor rolls an invocation check first; its result adds
    a bonus to the check you declared it on. Favor is not spent, but each call
    uses one of the week's invocations for that being, even a failed one.

    To call on a being, add '/invoke <being>[=<line>]' to the check:
        check <name> [at <band>] /invoke <being>[=<line>]
        check answer <call-id> /invoke <being>[=<line>]
        mission resolve <id> <n>/invoke <being>[=<line>]
        mission pick <id> <n>/invoke <being>[=<line>]
        persuade <character> /invoke <being>[=<line>]   (and the other social actions)

    The line is optional and describes how it shows; the room sees it, except
    for a secret faith, where the room hears only that you call on something.
    """

    key = "invoke"
    locks = "cmd:all()"
    help_category = "Social"
    action = None

    def func(self) -> None:
        from world.worship.invocation_services import (  # noqa: PLC0415
            find_being_to_invoke,
            invocation_bonus_table,
            invocation_options,
        )

        sheet = self.caller.character_sheet
        if sheet is None:
            self.msg("You have no character sheet.")
            return
        options = invocation_options(sheet)
        name = (self.args or "").strip()
        if name:
            being = find_being_to_invoke(sheet, name)
            options = [option for option in options if being and option.being.pk == being.pk]
            if not options:
                self.msg(f"You have no standing with a being called '{name}'.")
                return
        if not options:
            self.msg("You have no favor with any being to call on.")
            return
        lines = ["|wCall on favor|n"]
        for option in options:
            lines.extend(_render_invocation_option(option, detailed=bool(name)))
        bonuses = " · ".join(
            f"{row.outcome_name} +{row.bonus}" if row.bonus else f"{row.outcome_name}: none"
            for row in invocation_bonus_table()
        )
        lines.append(f"Bonus to the next check, by result: {bonuses}")
        lines.append("Add '/invoke <being>[=<line>]' to a check to call on one.")
        self.msg("\n".join(lines))


def _render_invocation_option(option: InvocationOption, *, detailed: bool) -> list[str]:
    """One being's line for ``invoke``: difficulty, uses left, or why it is refused."""
    from world.worship.invocation_services import difficulty_label  # noqa: PLC0415

    head = f"  {option.being.name} (favor {option.favor})"
    if option.difficulty is None or not option.can_invoke:
        return [f"{head}: {option.refusal}"]
    lines = [
        f"{head}: {difficulty_label(option.difficulty.points)}; "
        f"{option.uses_left} of {option.uses_per_week} left this week"
    ]
    if detailed:
        lines.append(f"    Base: {difficulty_label(option.difficulty.base_points)}")
        lines.extend(
            f"    {ease.label}: -{ease.points}" for ease in option.difficulty.eases if ease.points
        )
        lines.append("    Eases add; 15 points is one band; never below Trivial.")
    return lines
