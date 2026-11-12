"""Player channel REGISTRY actions (#3299).

Account-authorized (the ``ScheduleEventAction`` shape): every action runs with
``actor=None`` and reads the ``account`` kwarg, so a player with no puppet can still
chat, join or moderate. Shared by telnet ``CmdChannel`` (``commands/channels.py``) and
the REST ``ChannelMessageViewSet`` (``world/channels/views.py``). Thin wrappers over
``world.channels.services``: a ``ChannelError`` becomes a failure
``ActionResult(exc.user_message)``; no game logic lives here.

A channel is named by ``channel_id`` (web) or ``channel_name`` (telnet, matched
case-insensitively on the channel's display name). A message by ``message_id``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.constants import ActionCategory
from actions.kwarg_parsing import truthy_kwarg
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB

    from actions.prerequisites import Prerequisite
    from actions.types import ActionContext
    from world.channels.models import Channel, ChannelMessage, ChannelSubscription

_MSG_NO_ACCOUNT = "You must be logged in to use channels."
_MSG_WHICH_MESSAGE = "No such message."
_MSG_NOT_JOINED = "You aren't in that channel."
_MSG_WHICH_IDENTITY = "Pick a number from the list of who you can speak as."
_CHANNELS_CATEGORY = "channels"


def _resolve_channel(account: AccountDB, kwargs: dict[str, Any]) -> Channel | None:
    """The channel ``channel_id`` or ``channel_name`` names, or None."""
    from world.channels.models import Channel  # noqa: PLC0415
    from world.channels.services import channel_named  # noqa: PLC0415

    channel_id = kwargs.get("channel_id")
    if channel_id is not None:
        return Channel.objects.filter(pk=channel_id).select_related("organization").first()
    return channel_named(account, kwargs.get("channel_name") or "")


def _own_subscription(account: AccountDB, channel: Channel) -> ChannelSubscription | None:
    from world.channels.models import ChannelSubscription  # noqa: PLC0415

    return ChannelSubscription.objects.filter(account=account, channel=channel).first()


def _resolve_message(kwargs: dict[str, Any]) -> ChannelMessage | None:
    from world.channels.models import ChannelMessage  # noqa: PLC0415

    message_id = kwargs.get("message_id")
    if message_id is None:
        return None
    return (
        ChannelMessage.objects.filter(pk=message_id)
        .select_related("channel", "author_tenure__player_data__account")
        .first()
    )


class _AccountChannelAction(Action):
    """Base for account-authorized channel actions: no character prerequisites."""

    def get_prerequisites(self) -> list[Prerequisite]:
        return []


@dataclass
class PostToChannelAction(_AccountChannelAction):
    """Post a message to a channel as the subscription's chosen identity."""

    key: str = "post_to_channel"
    name: str = "Post to Channel"
    icon: str = "message-square"
    category: str = _CHANNELS_CATEGORY
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB | None,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.channels.services import post_to_channel  # noqa: PLC0415
        from world.channels.types import ChannelError  # noqa: PLC0415

        account = kwargs.get("account")
        if account is None:
            return ActionResult(success=False, message=_MSG_NO_ACCOUNT)
        channel = _resolve_channel(account, kwargs)
        if channel is None:
            return ActionResult(success=False, message=ChannelError.NO_SUCH_CHANNEL)
        try:
            message = post_to_channel(account=account, channel=channel, body=kwargs.get("body"))
        except ChannelError as exc:
            return ActionResult(success=False, message=exc.user_message)
        # No success line: live delivery already echoes the post to the author.
        return ActionResult(success=True, message="", data={"message_id": message.pk})


@dataclass
class JoinChannelAction(_AccountChannelAction):
    """Subscribe to a channel the account can reach."""

    key: str = "join_channel"
    name: str = "Join Channel"
    icon: str = "log-in"
    category: str = _CHANNELS_CATEGORY
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB | None,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.channels.services import subscribe  # noqa: PLC0415
        from world.channels.types import ChannelError  # noqa: PLC0415

        account = kwargs.get("account")
        if account is None:
            return ActionResult(success=False, message=_MSG_NO_ACCOUNT)
        channel = _resolve_channel(account, kwargs)
        if channel is None:
            return ActionResult(success=False, message=ChannelError.NO_SUCH_CHANNEL)
        try:
            subscription = subscribe(account, channel)
        except ChannelError as exc:
            return ActionResult(success=False, message=exc.user_message)
        message = f"You join {channel.display_name}."
        if subscription.display_tenure is None:
            message = f"{message} {ChannelError.NO_IDENTITY}"
        else:
            message = f"{message} You speak as {subscription.display_tenure.speaker_name}."
        return ActionResult(
            success=True, message=message, data={"subscription_id": subscription.pk}
        )


@dataclass
class LeaveChannelAction(_AccountChannelAction):
    """Unsubscribe from a channel."""

    key: str = "leave_channel"
    name: str = "Leave Channel"
    icon: str = "log-out"
    category: str = _CHANNELS_CATEGORY
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB | None,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.channels.services import unsubscribe  # noqa: PLC0415
        from world.channels.types import ChannelError  # noqa: PLC0415

        account = kwargs.get("account")
        if account is None:
            return ActionResult(success=False, message=_MSG_NO_ACCOUNT)
        channel = _resolve_channel(account, kwargs)
        if channel is None:
            return ActionResult(success=False, message=ChannelError.NO_SUCH_CHANNEL)
        if _own_subscription(account, channel) is None:
            return ActionResult(success=False, message=_MSG_NOT_JOINED)
        unsubscribe(account, channel)
        return ActionResult(success=True, message=f"You leave {channel.display_name}.")


@dataclass
class SetChannelMuteAction(_AccountChannelAction):
    """Mute or unmute a joined channel (``muted: bool``)."""

    key: str = "set_channel_mute"
    name: str = "Mute Channel"
    icon: str = "bell-off"
    category: str = _CHANNELS_CATEGORY
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB | None,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.channels.services import update_subscription  # noqa: PLC0415
        from world.channels.types import ChannelError  # noqa: PLC0415

        account = kwargs.get("account")
        if account is None:
            return ActionResult(success=False, message=_MSG_NO_ACCOUNT)
        channel = _resolve_channel(account, kwargs)
        if channel is None:
            return ActionResult(success=False, message=ChannelError.NO_SUCH_CHANNEL)
        subscription = _own_subscription(account, channel)
        if subscription is None:
            return ActionResult(success=False, message=ChannelError.NOT_SUBSCRIBED)
        muted = truthy_kwarg(kwargs.get("muted"))
        update_subscription(subscription, muted=muted)
        verb = "mute" if muted else "unmute"
        return ActionResult(success=True, message=f"You {verb} {channel.display_name}.")


@dataclass
class SetChannelIdentityAction(_AccountChannelAction):
    """Choose who to speak as in a joined channel.

    ``choice`` is a 1-based index into ``eligible_tenures(account, channel)``, the same
    list (same order) the telnet ``channel as <name>`` listing numbers.
    """

    key: str = "set_channel_identity"
    name: str = "Choose Channel Identity"
    icon: str = "user-round"
    category: str = _CHANNELS_CATEGORY
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB | None,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.channels.services import (  # noqa: PLC0415
            eligible_tenures,
            update_subscription,
        )
        from world.channels.types import ChannelError  # noqa: PLC0415

        account = kwargs.get("account")
        if account is None:
            return ActionResult(success=False, message=_MSG_NO_ACCOUNT)
        channel = _resolve_channel(account, kwargs)
        if channel is None:
            return ActionResult(success=False, message=ChannelError.NO_SUCH_CHANNEL)
        subscription = _own_subscription(account, channel)
        if subscription is None:
            return ActionResult(success=False, message=ChannelError.NOT_SUBSCRIBED)
        choices = eligible_tenures(account, channel)
        choice = kwargs.get("choice")
        if not isinstance(choice, int) or not 1 <= choice <= len(choices):
            return ActionResult(success=False, message=_MSG_WHICH_IDENTITY)
        tenure = choices[choice - 1]
        try:
            update_subscription(subscription, display_tenure=tenure)
        except ChannelError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=f"In {channel.display_name} you now speak as {tenure.speaker_name}.",
        )


@dataclass
class DeleteChannelMessageAction(_AccountChannelAction):
    """Staff: delete a channel message from every reader's history."""

    key: str = "delete_channel_message"
    name: str = "Delete Channel Message"
    icon: str = "trash-2"
    category: str = _CHANNELS_CATEGORY
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB | None,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.channels.services import delete_channel_message  # noqa: PLC0415
        from world.channels.types import ChannelError  # noqa: PLC0415

        account = kwargs.get("account")
        if account is None:
            return ActionResult(success=False, message=_MSG_NO_ACCOUNT)
        message = _resolve_message(kwargs)
        if message is None:
            return ActionResult(success=False, message=_MSG_WHICH_MESSAGE)
        try:
            delete_channel_message(message=message, staff_account=account)
        except ChannelError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(success=True, message="Message deleted.")


@dataclass
class BanChannelAuthorAction(_AccountChannelAction):
    """Staff: ban a message's author from its channel (``reason`` optional)."""

    key: str = "ban_channel_author"
    name: str = "Ban Channel Author"
    icon: str = "ban"
    category: str = _CHANNELS_CATEGORY
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB | None,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.channels.services import ban_channel_author  # noqa: PLC0415
        from world.channels.types import ChannelError  # noqa: PLC0415

        account = kwargs.get("account")
        if account is None:
            return ActionResult(success=False, message=_MSG_NO_ACCOUNT)
        message = _resolve_message(kwargs)
        if message is None:
            return ActionResult(success=False, message=_MSG_WHICH_MESSAGE)
        try:
            ban_channel_author(
                message=message, staff_account=account, reason=kwargs.get("reason") or ""
            )
        except ChannelError as exc:
            return ActionResult(success=False, message=exc.user_message)
        # Never name the author's account: the speaker label is the only handle shown.
        speaker = message.author_tenure.speaker_name
        return ActionResult(
            success=True,
            message=f"The player speaking as {speaker} is banned from "
            f"{message.channel.display_name}.",
        )
