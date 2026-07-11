"""Telnet rivalry commands (#2170).

Thin wrappers over ``world.scenes.friend_services`` — the telnet face of the declared-rivals
list, the antagonism counterpart to the friends list. A rivalry binds *this character's tenure*
to the target's tenure (re-roster-safe, alt-private). **Double opt-in**: a rivalry is only
*mutual* (and only then does it satisfy the RIVALS consent mode) once both sides have declared.
No business logic here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist

from commands.command import ArxCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from world.roster.models import RosterTenure

_NO_IDENTITY = "You have no character identity to act with."
_LOCK_ALL = "cmd:all()"


def _caller_tenure(command: ArxCommand) -> RosterTenure:
    try:
        entry = command.caller.sheet_data.roster_entry
    except (AttributeError, ObjectDoesNotExist) as exc:
        raise CommandError(_NO_IDENTITY) from exc
    tenure = entry.current_tenure if entry is not None else None
    if tenure is None:
        raise CommandError(_NO_IDENTITY)
    return tenure


def _target_tenure(command: ArxCommand, name: str) -> tuple[object, RosterTenure]:
    target = command.search_or_raise(name)
    try:
        entry = target.sheet_data.roster_entry
    except (AttributeError, ObjectDoesNotExist) as exc:
        msg = f"You can't name {target} a rival."
        raise CommandError(msg) from exc
    tenure = entry.current_tenure if entry is not None else None
    if tenure is None:
        msg = f"You can't name {target} a rival right now."
        raise CommandError(msg)
    return target, tenure


class CmdRival(ArxCommand):
    """Declare an IC rival — the antagonism-consent counterpart to a friend.

    Usage:
      rival <character>     — declare them your rival from THIS character

    A rivalry is **double opt-in**: it only becomes *mutual* — and only then may either of you
    aim your rivals-mode antagonism at the other — once they've declared you back. Out-of-band
    from IC affection; per-character (re-roster-safe, alt-private).
    """

    key = "+rival"
    aliases = ["rival"]
    locks = _LOCK_ALL

    def func(self) -> None:
        from world.scenes.friend_services import declare_rival, is_rival  # noqa: PLC0415

        name = (self.args or "").strip()
        if not name:
            self.msg("Usage: rival <character>.")
            return
        try:
            target, target_tenure = _target_tenure(self, name)
            caller_tenure = _caller_tenure(self)
            declare_rival(rivaler_tenure=caller_tenure, rival_tenure=target_tenure)
            if is_rival(owner_tenure=caller_tenure, rival_tenure=target_tenure):
                self.msg(f"You and {target} are now mutual rivals.")
            else:
                self.msg(
                    f"You've declared {target} a rival — the rivalry is mutual once they "
                    "declare you back."
                )
        except CommandError as err:
            self.msg(str(err))


class CmdUnrival(ArxCommand):
    """Withdraw your rival declaration of a character (from THIS character).

    Usage:
      unrival <character>
    """

    key = "+unrival"
    aliases = ["unrival"]
    locks = _LOCK_ALL

    def func(self) -> None:
        from world.scenes.friend_services import undeclare_rival  # noqa: PLC0415

        name = (self.args or "").strip()
        if not name:
            self.msg("Usage: unrival <character>.")
            return
        try:
            target, target_tenure = _target_tenure(self, name)
            undeclare_rival(rivaler_tenure=_caller_tenure(self), rival_tenure=target_tenure)
            self.msg(f"You've withdrawn your rival declaration of {target}.")
        except CommandError as err:
            self.msg(str(err))


class CmdRivals(ArxCommand):
    """List the rivals your current character has declared.

    Usage:
      rivals
    """

    key = "+rivals"
    aliases = ["rivals"]
    locks = _LOCK_ALL

    def func(self) -> None:
        from world.scenes.friend_services import is_rival, rivaled_tenures_for  # noqa: PLC0415

        try:
            caller_tenure = _caller_tenure(self)
        except CommandError as err:
            self.msg(str(err))
            return
        tenures = rivaled_tenures_for(caller_tenure).select_related(
            "roster_entry__character_sheet__character"
        )
        entries = []
        for tenure in tenures:
            character = tenure.roster_entry.character_sheet.character
            if character is None:
                continue
            mutual = is_rival(owner_tenure=caller_tenure, rival_tenure=tenure)
            entries.append(f"{character.key}{' (mutual)' if mutual else ''}")
        if not entries:
            self.msg("This character has declared no rivals.")
            return
        self.msg("|wYour declared rivals (this character):|n " + ", ".join(sorted(entries)))
