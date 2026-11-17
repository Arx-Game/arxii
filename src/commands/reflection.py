"""Telnet reflections (#5124): ``reflect`` lists what you can reflect on, and the pose and
journal commands take the reflection with their text.

    pose/reflect <deed, resonance or mire:Sinner>=<choice> <text>
    journal/reflect <deed, resonance or mire:Sinner>=<choice> title=<text> body=<text> ...

A deed is named by the number ``reflect`` shows beside it; the resonance that is unsettling
you is named by its name; the Mire you carry for a Sinner is named ``mire:`` and the Sinner's
name (``mire:Kalen``). A deed or a resonance takes ``embrace`` or ``disown``; the Mire takes
``absolve``, ``condemn`` or ``succumb``. No game logic lives here: the service resolves the
name and the action records the reflection.
"""

from __future__ import annotations

from typing import Any

from commands.command import ArxCommand
from commands.exceptions import CommandError
from world.magic.constants import BURDEN_REFLECTION_CHOICES, DEED_REFLECTION_CHOICES
from world.magic.exceptions import ReflectionError
from world.magic.services.reflection import (
    BURDEN_PREFIX,
    parse_reflection_choice,
    reflectable_for,
    resolve_reflection_target,
)

NO_SHEET = "You have no character sheet."
NOTHING_TO_REFLECT_ON = "You have nothing to reflect on."
REFLECT_USAGE = "<deed number, resonance or mire:Sinner>=<choice>"


def reflection_kwargs_and_rest(sheet: Any, args: str, *, usage: str) -> tuple[dict[str, Any], str]:
    """Split ``<target>=<choice> <rest>`` into the action's reflection kwargs and rest.

    ``usage`` is the whole command's usage line, shown when the shape is wrong. A target the
    player cannot reflect on is the service's own refusal, passed on as the command's error.
    """
    target_text, equals, after = args.strip().partition("=")
    choice_text, _, rest = after.strip().partition(" ")
    if not equals or not target_text.strip() or not choice_text:
        raise CommandError(usage)
    try:
        target = resolve_reflection_target(sheet, target_text)
        choice = parse_reflection_choice(choice_text, target)
    except ReflectionError as exc:
        raise CommandError(exc.user_message) from exc
    kwargs: dict[str, Any] = {"reflect_choice": choice}
    if target.grant is not None:
        kwargs["reflect_grant_id"] = target.grant.pk
    elif target.tether is not None:
        kwargs["reflect_tether_id"] = target.tether.pk
    else:
        kwargs["reflect_resonance_id"] = target.resonance.pk
    return kwargs, rest.strip()


def _warning(has_waiting: bool) -> str:
    return " (a reflection already waits; a new one replaces it)" if has_waiting else ""


def _words(choices: tuple[str, ...]) -> str:
    return "|".join(choice.lower() for choice in choices)


class CmdReflect(ArxCommand):
    """See what you can reflect on.

    Usage:
        reflect

    Lists the resonance that is unsettling you (named by its name), each deed you have not
    reflected on yet (named by its number), and the Mire you carry for each Sinner (named
    ``mire:`` and the Sinner's name). Write the reflection with a pose or a journal entry:

        pose/reflect <deed number or resonance>=<embrace|disown> <text>
        pose/reflect mire:<Sinner>=<absolve|condemn|succumb> <text>
        journal/reflect <deed number or resonance>=<embrace|disown> title=<text> body=<text>
        journal/reflect mire:<Sinner>=<absolve|condemn|succumb> title=<text> body=<text>

    Posting records the reflection and changes nothing yet. The room sees only the pose.
    """

    key = "reflect"
    locks = "cmd:all()"
    help_category = "Magic"
    action = None

    def func(self) -> None:
        sheet = self.caller.character_sheet
        if sheet is None:
            self.msg(NO_SHEET)
            return
        reflectable = reflectable_for(sheet)
        lines = [f"|w#{deed.grant.pk}|n {deed.label}" for deed in reflectable.deeds]
        if reflectable.unsettling is not None:
            waiting = _warning(reflectable.unsettling_has_waiting)
            lines.append(f"|w{reflectable.unsettling.name}|n - unsettling you{waiting}")
        lines.extend(
            f"|w{BURDEN_PREFIX}{burden.tether.target.primary_persona.name}|n - "
            f"{burden.label}{_warning(burden.has_waiting)}"
            for burden in reflectable.burdens
        )
        if not lines:
            self.msg(NOTHING_TO_REFLECT_ON)
            return
        if reflectable.burdens:
            lines.append(f"The Mire takes {_words(BURDEN_REFLECTION_CHOICES)}.")
        lines.append(
            f"Reflect with pose/reflect <name or #>=<{_words(DEED_REFLECTION_CHOICES)}> <text>."
        )
        self.msg("\n".join(lines))
