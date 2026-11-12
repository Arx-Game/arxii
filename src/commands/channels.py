"""Telnet player channel command (#3299).

One ``channel`` command (aliases ``chan``, ``channels``) on the AccountCmdSet, so it
works with or without a puppet. It replaces Evennia's stock ``@channel`` and takes no
``@channel`` alias. Parse, resolve, call the account-authorized channel Actions
(``actions/definitions/channels.py``); no business logic lives here. Incoming channel
messages reach a telnet session through live delivery
(``world.channels.services.deliver_channel_message``), not through this command.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from evennia.accounts.models import AccountDB

from commands.command import ArxCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from actions.base import Action
    from world.channels.models import Channel, ChannelSubscription

_USAGE = (
    "Usage: channel [list] | channel join|leave|mute|unmute <name> | "
    "channel as <name>[=<number>] | channel <name>=<message>"
)
_SUBVERB_LIST = "list"
_SUBVERB_AS = "as"
# Subverbs that take a bare channel name. A line with "=" after one of these words is a
# post to a channel whose name starts with that word ("channel Leave Takers=hello").
_SUBVERB_JOIN = "join"
_SUBVERB_LEAVE = "leave"
_SUBVERB_MUTE = "mute"
_SUBVERB_UNMUTE = "unmute"
_NAME_SUBVERBS = frozenset({_SUBVERB_JOIN, _SUBVERB_LEAVE, _SUBVERB_MUTE, _SUBVERB_UNMUTE})


class CmdChannel(ArxCommand):
    """Talk on out-of-character channels.

    Syntax:
        channel
        channel list
        channel join <name>
        channel leave <name>
        channel mute <name>
        channel unmute <name>
        channel as <name>
        channel as <name>=<number>
        channel <name>=<message>

    Bare ``channel`` lists the channels you can use. ``channel as <name>`` lists
    who you can speak as there; pick one by its number. Channel names are not
    case-sensitive.
    """

    key = "channel"
    aliases = ("chan", "channels")
    locks = "cmd:all()"
    help_category = "Comms"
    action = None  # routes to multiple actions

    def func(self) -> None:
        try:
            self._dispatch()
        except CommandError as err:
            self.msg(str(err))

    def _dispatch(self) -> None:
        args = (self.args or "").strip()
        if not args:
            self._list()
            return
        tokens = args.split(None, 1)
        first = tokens[0].lower()
        rest = tokens[1].strip() if len(tokens) > 1 else ""

        if first == _SUBVERB_LIST and not rest:
            self._list()
        elif first in _NAME_SUBVERBS and rest and "=" not in rest:
            self._name_verb(first, rest)
        elif first == _SUBVERB_AS and rest:
            self._identity(args, rest)
        elif "=" in args:
            self._post(args)
        else:
            raise CommandError(_USAGE)

    # ------------------------------------------------------------------
    # Helpers

    def _account(self) -> AccountDB:
        """The caller's account: the caller itself with no puppet, else its account."""
        caller = self.caller
        account = caller if isinstance(caller, AccountDB) else caller.account
        if account is None:
            msg = "You must be logged in to use channels."
            raise CommandError(msg)
        return account

    def _run(self, action: Action, **kwargs: Any) -> None:
        result = action.run(actor=None, account=self._account(), **kwargs)
        if result.message:
            self.msg(result.message)

    # ------------------------------------------------------------------
    # Subverbs

    def _list(self) -> None:
        from world.channels.models import ChannelSubscription  # noqa: PLC0415
        from world.channels.services import accessible_channels_for  # noqa: PLC0415

        account = self._account()
        channels: list[Channel] = list(accessible_channels_for(account))
        if not channels:
            self.msg("You have no channels.")
            return
        subscriptions: dict[int, ChannelSubscription] = {
            sub.channel_id: sub
            for sub in ChannelSubscription.objects.filter(
                account=account, channel__in=channels
            ).select_related("display_tenure__roster_entry__character_sheet__character")
        }
        lines = ["|wChannels|n"]
        lines.extend(
            f"  {channel.display_name} ({channel.get_kind_display()}) "
            f"{self._state(subscriptions.get(channel.pk))}"
            for channel in sorted(channels, key=lambda c: c.display_name.lower())
        )
        self.msg("\n".join(lines))

    @staticmethod
    def _state(subscription: ChannelSubscription | None) -> str:
        if subscription is None:
            return "- not joined"
        state = "muted" if subscription.muted else "joined"
        tenure = subscription.display_tenure
        speaker = tenure.speaker_name if tenure is not None else "nobody chosen yet"
        return f"- {state}, speaking as {speaker}"

    def _name_verb(self, subverb: str, name: str) -> None:
        from actions.definitions.channels import (  # noqa: PLC0415
            JoinChannelAction,
            LeaveChannelAction,
            SetChannelMuteAction,
        )

        if subverb == _SUBVERB_JOIN:
            self._run(JoinChannelAction(), channel_name=name)
        elif subverb == _SUBVERB_LEAVE:
            self._run(LeaveChannelAction(), channel_name=name)
        else:
            self._run(SetChannelMuteAction(), channel_name=name, muted=subverb == _SUBVERB_MUTE)

    def _identity(self, args: str, rest: str) -> None:
        """``channel as <name>`` lists the choices; ``channel as <name>=<n>`` picks one.

        A right-hand side that is not a number is a post to a channel whose name starts
        with "as" ("channel As You Wish=hello").
        """
        from actions.definitions.channels import SetChannelIdentityAction  # noqa: PLC0415

        if "=" not in rest:
            self._list_identities(rest)
            return
        name, choice = (part.strip() for part in rest.split("=", 1))
        if not choice.isdigit():
            self._post(args)
            return
        self._run(SetChannelIdentityAction(), channel_name=name, choice=int(choice))

    def _list_identities(self, name: str) -> None:
        from world.channels.services import channel_named, eligible_tenures  # noqa: PLC0415
        from world.channels.types import ChannelError  # noqa: PLC0415

        account = self._account()
        channel = channel_named(account, name)
        if channel is None:
            raise CommandError(ChannelError.NO_SUCH_CHANNEL)
        tenures = eligible_tenures(account, channel)
        if not tenures:
            raise CommandError(ChannelError.INELIGIBLE_IDENTITY)
        lines = [f"|wWho you can speak as in {channel.display_name}|n"]
        lines.extend(f"  {i}. {tenure.speaker_name}" for i, tenure in enumerate(tenures, 1))
        lines.append(f"Pick one with: channel as {channel.display_name}=<number>")
        self.msg("\n".join(lines))

    def _post(self, args: str) -> None:
        from actions.definitions.channels import PostToChannelAction  # noqa: PLC0415

        name, body = (part.strip() for part in args.split("=", 1))
        if not name:
            raise CommandError(_USAGE)
        self._run(PostToChannelAction(), channel_name=name, body=body)
