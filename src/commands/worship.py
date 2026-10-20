"""Telnet faces of prayer and the GM-sent vision (#3779).

Thin: parsing only, every rule lives in the actions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from commands.command import ArxCommand

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
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
        lines.extend(_render_worn(option))
        lines.append("    Eases add; 15 points is one band; never below Trivial.")
    return lines


def _render_worn(option: InvocationOption) -> list[str]:
    """The worn pieces carrying a facet the being favors, for ``invoke <being>`` (#4520):
    what each means, whether it counts and the ease it gives."""
    worn = option.worn
    if worn is None or not worn.pieces:
        return []
    lines = []
    for piece in worn.pieces:
        head = f"    Worn: {piece.item_name} ({piece.facet_name}, favored)"
        if piece.counted:
            reasons = ", ".join(
                f"{signal.kind.replace('_', ' ')} {signal.points}"
                for signal in piece.meaning.signals
            )
            lines.append(
                f"{head}: {piece.points} points x {piece.ease_per_point} = eased {piece.ease}"
                f"; {reasons}"
            )
        elif piece.points == 0:
            lines.append(f"{head}: bought; no history beyond holding it, so it counts for nothing")
        else:
            lines.append(
                f"{head}: only the {worn.items_counted_max} pieces with the most meaning count"
            )
    if worn.raw_ease > worn.ease:
        lines.append(
            f"    What you wear eases at most {worn.ease_cap} (it would ease {worn.raw_ease})."
        )
    if worn.earning_percent:
        lines.append(
            f"    Wearing these adds {worn.earning_percent}% to your earning rate with "
            f"{option.being.name}."
        )
    return lines


_SWITCH_CLOSE = "close"


class CmdPledge(ArxCommand):
    """Pledge yourself to a being, follow your pledge, and close it.

    Usage:
        pledge                                  - your pledge and what it has earned
        pledge <being>                          - the pledges a being offers you
        pledge <being>/<pledge>[=<prayer>]      - take one, with optional words
        pledge/close                            - close it with its closing rite

    A pledge has a favor target and a span. Every favor you earn with the being
    after pledging counts toward it: deeds that grant a resonance it values,
    sacrifices at its shrine, its rites, holy-site prayer and ceremony offerings.
    Reaching the target does not close it; its closing rite does, in a live
    scene. A first failed close leaves one more try within the span.
    """

    key = "pledge"
    takes_switches = True
    locks = "cmd:all()"
    help_category = "Social"
    action = None

    def func(self) -> None:
        sheet = self.caller.character_sheet
        if sheet is None:
            self.msg("You have no character sheet.")
            return
        switches = {switch.lower() for switch in self.switches}
        raw = (self.args or "").strip()
        if _SWITCH_CLOSE in switches:
            from actions.definitions.worship import ClosePledgeAction  # noqa: PLC0415

            result = ClosePledgeAction().run(actor=self.caller)
            if result.message:
                self.msg(result.message)
            return
        if not raw:
            self.msg(_render_own_pledge(sheet))
            return
        target, _, prayer = raw.partition("=")
        being_name, slash, pledge_name = (part.strip() for part in target.partition("/"))
        if not slash:
            self.msg(_render_offered(sheet, being_name))
            return
        from actions.definitions.worship import TakePledgeAction  # noqa: PLC0415

        result = TakePledgeAction().run(
            actor=self.caller,
            being_name=being_name,
            pledge_name=pledge_name,
            prayer=prayer.strip(),
        )
        if result.message:
            self.msg(result.message)


def _render_own_pledge(sheet: CharacterSheet) -> str:
    from django.utils import timezone  # noqa: PLC0415
    from django.utils.timesince import timeuntil  # noqa: PLC0415

    from world.worship.constants import PledgeState  # noqa: PLC0415
    from world.worship.pledge_services import latest_pledge_for, pledge_card  # noqa: PLC0415

    details = latest_pledge_for(sheet)
    if details is None:
        return "You hold no pledge. 'pledge <being>' lists what a being offers."
    card = pledge_card(details)
    being = details.pledge.being.name
    head = (
        f"|wPledge|n to {being}: {details.pledge.name}. "
        f"{card.progress} of {card.target} favor since pledging."
    )
    if card.state == PledgeState.READY:
        head += f" Ready to close. {timeuntil(card.time_limit, timezone.now())} left."
    elif card.state == PledgeState.OPEN:
        head += f" {timeuntil(card.time_limit, timezone.now())} left."
    else:
        head += f" {PledgeState(card.state).label}."
    lines = [head]
    lines.extend(f"  {line.label}: {line.calculation}" for line in card.credits)
    if card.retry_available:
        lines.append("Your first close failed; one more try is left within the span.")
    return "\n".join(lines)


def _render_offered(sheet: CharacterSheet, being_name: str) -> str:
    from world.worship.models import WorshippedBeing  # noqa: PLC0415
    from world.worship.pledge_services import offered_pledges, service_terms  # noqa: PLC0415

    being = WorshippedBeing.objects.filter(name__iexact=being_name, is_active=True).first()
    if being is None:
        return f"No being '{being_name}' is known."
    pledges = offered_pledges(being)
    if not pledges:
        return f"{being.name} offers no pledge."
    lines = [f"|wPledges {being.name} offers|n"]
    for pledge in pledges:
        weeks = "game week" if pledge.span_weeks == 1 else "game weeks"
        lines.append(
            f"  {pledge.name}: favor target {pledge.favor_target} within "
            f"{pledge.span_weeks} {weeks}; closed with {pledge.closing_rite.name}."
        )
    terms = service_terms(sheet, being)
    lines.append(f"What earns favor with {being.name} for you:")
    lines.extend(f"  {line.label}: {line.amount}" for line in terms.lines)
    lines.append(
        f"  Your earning rate: {terms.rate.total}% (applies to all). Base favor from deeds "
        f"is capped at {terms.weekly_deed_cap} a week, before your earning rate."
    )
    lines.append(f"Take one with 'pledge {being.name}/<pledge>[=<prayer>]'.")
    return "\n".join(lines)


class CmdSacrifice(ArxCommand):
    """Sacrifice items you carry at a being's shrine or temple.

    Usage:
        sacrifice <item>[,<item>...][=<being>]

    The items are destroyed and feed the being's worship pool, and you earn
    favor with the being in proportion to their value: more for an item carrying
    a facet the being favors. Name the being when the place is holy to two. A
    being your GM table stewards takes a sacrifice anywhere: name it.
    """

    key = "sacrifice"
    locks = "cmd:all()"
    help_category = "Social"
    action = None

    def func(self) -> None:
        from actions.definitions.worship import SacrificeAction  # noqa: PLC0415

        raw = (self.args or "").strip()
        items, _, being_name = raw.partition("=")
        names = [name.strip() for name in items.split(",") if name.strip()]
        if not names:
            self.msg("Usage: sacrifice <item>[,<item>...][=<being>]")
            return
        result = SacrificeAction().run(
            actor=self.caller, item_names=names, being_name=being_name.strip()
        )
        if result.message:
            self.msg(result.message)
