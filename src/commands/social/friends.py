"""Telnet friends-list commands (#1727).

Thin wrappers over ``world.scenes.friend_services`` — the telnet face of the OOC friends list. A
friendship binds *this character's tenure* to the target character's tenure (re-roster-safe,
alt-private). No business logic here.
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
_ALL = "all"


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
        msg = f"You can't friend {target}."
        raise CommandError(msg) from exc
    tenure = entry.current_tenure if entry is not None else None
    if tenure is None:
        msg = f"You can't friend {target} right now."
        raise CommandError(msg)
    return target, tenure


class CmdFriend(ArxCommand):
    """Add an OOC friend — a trusted RP partner.

    Usage:
      friend <character>       — friend them from THIS character (default)
      friend/all <character>   — friend them from ALL your characters

    A friend gets a login/logoff alert for you (a watch list) and may be allowed to act on you under
    the friends consent mode. Friendships are per-character: `friend/all` adds one for each of your
    characters, each removable on its own. Out-of-character — separate from IC relationships.
    """

    key = "+friend"
    aliases = ["friend"]
    locks = _LOCK_ALL

    def func(self) -> None:
        from world.scenes.friend_services import (  # noqa: PLC0415
            add_friend,
            add_friend_all_characters,
        )

        name = (self.args or "").strip()
        if not name:
            self.msg("Usage: friend <character>  (or friend/all <character>).")
            return
        try:
            target, target_tenure = _target_tenure(self, name)
            if _ALL in self.switches:
                from evennia_extensions.models import PlayerData  # noqa: PLC0415

                player_data, _ = PlayerData.objects.get_or_create(account=self.account)
                add_friend_all_characters(player_data=player_data, friend_tenure=target_tenure)
                self.msg(f"All your characters now count {target} as a friend.")
            else:
                add_friend(friender_tenure=_caller_tenure(self), friend_tenure=target_tenure)
                self.msg(f"You added {target} as a friend (from this character).")
        except CommandError as err:
            self.msg(str(err))


class CmdUnfriend(ArxCommand):
    """Remove an OOC friend from THIS character (your other characters keep theirs).

    Usage:
      unfriend <character>
    """

    key = "+unfriend"
    aliases = ["unfriend"]
    locks = _LOCK_ALL

    def func(self) -> None:
        from world.scenes.friend_services import remove_friend  # noqa: PLC0415

        name = (self.args or "").strip()
        if not name:
            self.msg("Usage: unfriend <character>.")
            return
        try:
            target, target_tenure = _target_tenure(self, name)
            remove_friend(friender_tenure=_caller_tenure(self), friend_tenure=target_tenure)
            self.msg(f"You removed {target} as a friend (from this character).")
        except CommandError as err:
            self.msg(str(err))


class CmdFriends(ArxCommand):
    """List the friends of your current character.

    Usage:
      friends
    """

    key = "+friends"
    aliases = ["friends"]
    locks = _LOCK_ALL

    def func(self) -> None:
        from world.scenes.friend_services import friended_tenures_for  # noqa: PLC0415

        try:
            caller_tenure = _caller_tenure(self)
        except CommandError as err:
            self.msg(str(err))
            return
        tenures = friended_tenures_for(caller_tenure).select_related(
            "roster_entry__character_sheet__character"
        )
        names = [
            tenure.roster_entry.character_sheet.character.key
            for tenure in tenures
            if tenure.roster_entry.character_sheet.character is not None
        ]
        if not names:
            self.msg("This character has no friends listed.")
            return
        self.msg("|wYour friends (this character):|n " + ", ".join(sorted(names)))
