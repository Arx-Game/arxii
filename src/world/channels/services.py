"""Services for player channels (#3299).

Access, identity, subscription, posting, live delivery, moderation, provisioning and
history pruning. Every refusal raises ``ChannelError`` with a user-safe message.

Anonymity: a message is shown under its author tenure's ``speaker_name``; no service here
returns or pushes an account name, account id, or another account's tenures.

Access is always re-derived from live state (channel active, org not covert, current
tenure holding an active membership, no ban). A ``ChannelSubscription`` row is never
proof of access.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import F, Q, QuerySet, Window
from django.db.models.functions import RowNumber
from django.utils import timezone
from evennia.utils.logger import log_trace

from web.webclient.message_types import ChannelMessagePayload
from world.channels.constants import (
    CHANNEL_HISTORY_CAP,
    CHANNEL_MESSAGE_MAX_LENGTH,
    PUBLIC_CHANNEL_NAME,
    ChannelKind,
    ChannelNotificationLevel,
)
from world.channels.models import Channel, ChannelBan, ChannelMessage, ChannelSubscription
from world.channels.types import ChannelError
from world.roster.models import RosterTenure
from world.scenes.block_services import blocked_player_ids_for
from world.scenes.interaction_services import WEB_PROTOCOL_KEYS
from world.scenes.mute_services import account_muter_player_ids, muted_player_ids_for
from world.societies.houses.models import FealtyEdge
from world.societies.models import Organization, OrganizationMembership

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from evennia_extensions.models import PlayerData


class Unset:
    """Marks an argument the caller did not pass, where ``None`` is a real value."""


UNSET = Unset()

# Stored-name slot width (Channel.name max_length) and the clash suffix for org channels.
_CHANNEL_NAME_MAX = 80
_ORG_NAME_SUFFIX = " (org)"

PUBLIC_CHANNEL_DESCRIPTION = (
    "The game-wide out-of-character channel. Everyone can read and post here."
)

# Tenure -> active membership path. All three conditions must sit in ONE filter() call so
# they apply to the same membership row.
_TENURE_MEMBERSHIP = "roster_entry__character_sheet__personas__organization_memberships"


# ---------------------------------------------------------------- players


def _player_data(account: AccountDB) -> PlayerData | None:
    try:
        return account.player_data
    except ObjectDoesNotExist:
        return None


def hidden_author_player_ids(account: AccountDB) -> set[int]:
    """Players whose channel rows this account sees hidden: account blocks, either way."""
    player = _player_data(account)
    return blocked_player_ids_for(player) if player is not None else set()


def _muted_author_player_ids(account: AccountDB) -> set[int]:
    player = _player_data(account)
    return muted_player_ids_for(viewer_player=player) if player is not None else set()


# ---------------------------------------------------------------- org cascade


def _org_cascade_ids(organization: Organization) -> list[int]:
    """The org and its vassals, recursively (house cascade, #1884), with every covert
    vassal's WHOLE branch cut: neither the covert vassal nor anything sworn beneath it
    reaches the liege's channel (a sub-vassal's presence would hint at the covert link).
    Mirrors ``_org_ids_reachable_for``, which walks the same edges upward."""
    found = [organization.pk]
    seen = {organization.pk}
    frontier = {organization.pk}
    while frontier:
        vassal_ids = set(
            FealtyEdge.objects.filter(liege_id__in=frontier, vassal__is_covert=False)
            .exclude(vassal_id__in=seen)
            .values_list("vassal_id", flat=True)
        )
        found.extend(sorted(vassal_ids))
        seen |= vassal_ids
        frontier = vassal_ids
    return found


def _membership_tenure_q(org_ids: list[int]) -> Q:
    return Q(
        **{
            f"{_TENURE_MEMBERSHIP}__organization_id__in": org_ids,
            f"{_TENURE_MEMBERSHIP}__left_at__isnull": True,
            f"{_TENURE_MEMBERSHIP}__exiled_at__isnull": True,
        }
    )


def _org_ids_reachable_for(account: AccountDB) -> set[int]:
    """Org ids whose channel this account's current tenures reach: each non-covert org a
    current tenure holds an active membership in, plus every liege above it, stopping at a
    covert liege (its branch is cut, as in ``_org_cascade_ids``)."""
    start = set(
        OrganizationMembership.objects.filter(
            left_at__isnull=True,
            exiled_at__isnull=True,
            organization__is_covert=False,
            persona__character_sheet__roster_entry__tenures__player_data_id=account.pk,
            persona__character_sheet__roster_entry__tenures__end_date__isnull=True,
        ).values_list("organization_id", flat=True)
    )
    found = set(start)
    frontier = start
    while frontier:
        lieges = set(
            FealtyEdge.objects.filter(vassal_id__in=frontier, liege__is_covert=False).values_list(
                "liege_id", flat=True
            )
        )
        frontier = lieges - found
        found |= frontier
    return found


# ---------------------------------------------------------------- access


def _is_banned(account: AccountDB, channel: Channel) -> bool:
    return ChannelBan.objects.filter(channel=channel, account=account).exists()


def accessible_channels_for(account: AccountDB) -> QuerySet[Channel]:
    """Active channels this account may read and post in right now."""
    allowed = Q(kind=ChannelKind.PUBLIC) | Q(
        kind=ChannelKind.ORG,
        organization__is_covert=False,
        organization_id__in=_org_ids_reachable_for(account),
    )
    if account.is_staff:
        allowed |= Q(kind=ChannelKind.STAFF)
    banned_ids = ChannelBan.objects.filter(account=account).values("channel_id")
    return (
        Channel.objects.filter(allowed, is_active=True)
        .exclude(pk__in=banned_ids)
        .select_related("organization")
    )


def can_access_channel(account: AccountDB, channel: Channel) -> bool:
    if not channel.is_active or _is_banned(account, channel):
        return False
    if channel.kind == ChannelKind.PUBLIC:
        return True
    if channel.kind == ChannelKind.STAFF:
        return bool(account.is_staff)
    if channel.organization is None or channel.organization.is_covert:
        return False
    return _eligible_tenure_qs(account, channel).exists()


# ---------------------------------------------------------------- identity


def _eligible_tenure_qs(account: AccountDB, channel: Channel) -> QuerySet[RosterTenure]:
    qs = RosterTenure.objects.current().filter(player_data_id=account.pk)
    if channel.kind == ChannelKind.ORG:
        organization = channel.organization
        if organization is None or organization.is_covert:
            return qs.none()
        qs = qs.filter(_membership_tenure_q(_org_cascade_ids(organization))).distinct()
    return qs


def eligible_tenures(account: AccountDB, channel: Channel) -> list[RosterTenure]:
    """The account's current tenures that may speak in ``channel``, by character name."""
    return list(
        _eligible_tenure_qs(account, channel)
        .select_related("roster_entry__character_sheet__character")
        .order_by("roster_entry__character_sheet__character__db_key", "pk")
    )


def default_tenure_for(account: AccountDB, channel: Channel) -> RosterTenure | None:
    """The tenure of the puppeted character (else of the selected character), if it is
    eligible here; otherwise None. Never falls back to "first eligible"."""
    eligible = {t.roster_entry.character_sheet_id: t for t in eligible_tenures(account, channel)}
    puppets = [p for p in account.get_puppeted_characters() if p is not None]
    if puppets:
        for puppet in puppets:
            if puppet.pk in eligible:
                return eligible[puppet.pk]
        return None
    player = _player_data(account)
    entry = player.selected_entry if player is not None else None
    if entry is None:
        return None
    return eligible.get(entry.character_sheet_id)


def _check_identity(account: AccountDB, channel: Channel, tenure: RosterTenure) -> None:
    if not _eligible_tenure_qs(account, channel).filter(pk=tenure.pk).exists():
        raise ChannelError(ChannelError.INELIGIBLE_IDENTITY)


# ---------------------------------------------------------------- subscriptions


def _require_access(account: AccountDB, channel: Channel) -> None:
    # Ban first: a ban also removes access, and the player should hear why.
    if _is_banned(account, channel):
        raise ChannelError(ChannelError.BANNED)
    if not can_access_channel(account, channel):
        raise ChannelError(ChannelError.NO_ACCESS)


def subscribe(account: AccountDB, channel: Channel) -> ChannelSubscription:
    """Join ``channel`` (idempotent), pre-filling the speaking identity."""
    _require_access(account, channel)
    existing = ChannelSubscription.objects.filter(account=account, channel=channel).first()
    if existing is not None:
        return existing
    return ChannelSubscription.objects.create(
        account=account,
        channel=channel,
        display_tenure=default_tenure_for(account, channel),
    )


def update_subscription(  # noqa: PLR0913 - one keyword per independently settable preference
    subscription: ChannelSubscription,
    *,
    display_tenure: RosterTenure | None | Unset = UNSET,
    muted: bool | Unset = UNSET,
    collapsed: bool | Unset = UNSET,
    notification_level: str | Unset = UNSET,
    sort_order: int | Unset = UNSET,
) -> ChannelSubscription:
    """Change any subset of a subscription's preferences."""
    fields: list[str] = []
    if not isinstance(display_tenure, Unset):
        if display_tenure is not None:
            _check_identity(subscription.account, subscription.channel, display_tenure)
        subscription.display_tenure = display_tenure
        fields.append("display_tenure")
    if not isinstance(muted, Unset):
        subscription.muted = muted
        fields.append("muted")
    if not isinstance(collapsed, Unset):
        subscription.collapsed = collapsed
        fields.append("collapsed")
    if not isinstance(notification_level, Unset):
        subscription.notification_level = notification_level
        fields.append("notification_level")
    if not isinstance(sort_order, Unset):
        subscription.sort_order = sort_order
        fields.append("sort_order")
    if fields:
        subscription.save(update_fields=fields)
    return subscription


def unsubscribe(account: AccountDB, channel: Channel) -> None:
    ChannelSubscription.objects.filter(account=account, channel=channel).delete()


# ---------------------------------------------------------------- posting


def post_to_channel(*, account: AccountDB, channel: Channel, body: str) -> ChannelMessage:
    """Post ``body`` as the subscription's chosen tenure and deliver it live."""
    text = (body or "").strip()
    if not text:
        raise ChannelError(ChannelError.EMPTY)
    if len(text) > CHANNEL_MESSAGE_MAX_LENGTH:
        raise ChannelError(ChannelError.TOO_LONG)
    _require_access(account, channel)
    subscription = ChannelSubscription.objects.filter(account=account, channel=channel).first()
    if subscription is None:
        raise ChannelError(ChannelError.NOT_SUBSCRIBED)
    tenure = subscription.display_tenure
    if tenure is None:
        raise ChannelError(ChannelError.NO_IDENTITY)
    # Re-validated at post time: the player may have left the org or ended the tenure.
    _check_identity(account, channel, tenure)
    with transaction.atomic():
        message = ChannelMessage.objects.create(channel=channel, author_tenure=tenure, body=text)
        subscription.last_read_at = message.created_at
        subscription.save(update_fields=["last_read_at"])
    deliver_channel_message(message)
    return message


# ---------------------------------------------------------------- delivery


def _account_ids_with_access(channel: Channel, account_ids: list[int]) -> set[int]:
    """Batch form of ``can_access_channel`` over candidate account ids."""
    if not channel.is_active or not account_ids:
        return set()
    banned = set(ChannelBan.objects.filter(channel=channel).values_list("account_id", flat=True))
    candidates = [pk for pk in account_ids if pk not in banned]
    if channel.kind == ChannelKind.PUBLIC:
        return set(candidates)
    if channel.kind == ChannelKind.STAFF:
        from evennia.accounts.models import AccountDB  # noqa: PLC0415

        return set(
            AccountDB.objects.filter(pk__in=candidates, is_staff=True).values_list("pk", flat=True)
        )
    organization = channel.organization
    if organization is None or organization.is_covert:
        return set()
    return set(
        RosterTenure.objects.current()
        .filter(_membership_tenure_q(_org_cascade_ids(organization)))
        .filter(player_data_id__in=candidates)
        .values_list("player_data_id", flat=True)
    )


def _send(subscription: ChannelSubscription, message: ChannelMessage, *, is_own: bool) -> None:
    channel = message.channel
    speaker = message.author_tenure.speaker_name
    payload = asdict(
        ChannelMessagePayload(
            message_id=message.pk,
            channel_id=channel.pk,
            channel_name=channel.display_name,
            speaker=speaker,
            body=message.body,
            created_at=message.created_at.isoformat(),
            is_own=is_own,
            notification_level=subscription.notification_level,
        )
    )
    line = f"[{channel.display_name}] {speaker}: {message.body}"
    for session in subscription.account.sessions.all():
        if str(session.protocol_key or "") in WEB_PROTOCOL_KEYS:
            session.msg(channel_message=((), payload))
        else:
            session.msg(text=(line, {"type": "channel"}))


def deliver_channel_message(message: ChannelMessage) -> None:
    """Push ``message`` live to every subscriber who may see it, the author included."""
    channel = message.channel
    author_player = message.author_tenure.player_data
    subscriptions = list(channel.subscriptions.select_related("account"))
    reader_ids = [s.account_id for s in subscriptions if s.account_id != author_player.pk]
    allowed = _account_ids_with_access(channel, reader_ids)
    blocked = blocked_player_ids_for(author_player)
    muting = account_muter_player_ids(target_player=author_player)
    for subscription in subscriptions:
        is_own = subscription.account_id == author_player.pk
        if not is_own and (
            subscription.muted
            or subscription.account_id not in allowed
            or subscription.account_id in blocked
            or subscription.account_id in muting
        ):
            continue
        try:
            _send(subscription, message, is_own=is_own)
        except Exception:  # noqa: BLE001 - best-effort push; the message row is already saved
            log_trace(
                f"channel push failed for message={message.pk} subscription={subscription.pk}"
            )


# ---------------------------------------------------------------- reading


def history_for(account: AccountDB, channel: Channel) -> QuerySet[ChannelMessage]:
    """The channel's messages for this reader, OOC-muted authors dropped. Blocked authors
    stay in (the serializer hides them via ``hidden_author_player_ids``)."""
    return (
        channel.messages.exclude(
            author_tenure__player_data_id__in=_muted_author_player_ids(account)
        )
        .select_related("author_tenure__roster_entry__character_sheet__character")
        .order_by("created_at", "pk")
    )


def unread_count(subscription: ChannelSubscription) -> int:
    """Unread messages since ``last_read_at``; 0 for a muted channel or level NONE."""
    if subscription.muted or subscription.notification_level == ChannelNotificationLevel.NONE:
        return 0
    account = subscription.account
    excluded = {account.pk} | _muted_author_player_ids(account) | hidden_author_player_ids(account)
    qs = subscription.channel.messages.exclude(author_tenure__player_data_id__in=excluded)
    if subscription.last_read_at is not None:
        qs = qs.filter(created_at__gt=subscription.last_read_at)
    return qs.count()


def mark_read(subscription: ChannelSubscription) -> None:
    subscription.last_read_at = timezone.now()
    subscription.save(update_fields=["last_read_at"])


# ---------------------------------------------------------------- moderation


def _require_staff(staff_account: AccountDB) -> None:
    if not staff_account.is_staff:
        raise ChannelError(ChannelError.NOT_STAFF)


def delete_channel_message(*, message: ChannelMessage, staff_account: AccountDB) -> None:
    _require_staff(staff_account)
    message.delete()


def ban_channel_author(
    *, message: ChannelMessage, staff_account: AccountDB, reason: str = ""
) -> ChannelBan:
    """Ban the message author's account from the channel and drop its subscription."""
    _require_staff(staff_account)
    channel = message.channel
    account = message.author_tenure.player_data.account
    with transaction.atomic():
        ban, _ = ChannelBan.objects.get_or_create(
            channel=channel,
            account=account,
            defaults={"banned_by": staff_account, "reason": reason},
        )
        ChannelSubscription.objects.filter(account=account, channel=channel).delete()
    return ban


# ---------------------------------------------------------------- provisioning


def provision_org_channel(organization: Organization) -> Channel | None:
    """Get or create the ORG channel for ``organization``; None for a covert org."""
    if organization.is_covert:
        return None
    existing = Channel.objects.filter(organization=organization).first()
    if existing is not None:
        return existing
    name = organization.name[:_CHANNEL_NAME_MAX]
    # PUBLIC_CHANNEL_NAME is reserved for the public channel, so an org named "Public"
    # takes the suffix and ensure_public_channel never meets an ORG row in that slot.
    if name == PUBLIC_CHANNEL_NAME or Channel.objects.filter(name=name).exists():
        name = organization.name[: _CHANNEL_NAME_MAX - len(_ORG_NAME_SUFFIX)] + _ORG_NAME_SUFFIX
        if Channel.objects.filter(name=name).exists():
            suffix = f" (org {organization.pk})"
            name = organization.name[: _CHANNEL_NAME_MAX - len(suffix)] + suffix
    return Channel.objects.create(name=name, kind=ChannelKind.ORG, organization=organization)


def ensure_public_channel() -> Channel:
    """Get or create the PUBLIC channel. Matches on name AND kind, so a non-public row that
    somehow holds the reserved name is never returned as the public channel."""
    clash = (
        Channel.objects.filter(name=PUBLIC_CHANNEL_NAME).exclude(kind=ChannelKind.PUBLIC).first()
    )
    if clash is not None:
        msg = (
            f"Channel {clash.pk} ({clash.kind}) holds the reserved public channel name "
            f"{PUBLIC_CHANNEL_NAME!r}; rename it before provisioning the public channel."
        )
        raise ValueError(msg)
    channel, _ = Channel.objects.get_or_create(
        name=PUBLIC_CHANNEL_NAME,
        kind=ChannelKind.PUBLIC,
        defaults={"description": PUBLIC_CHANNEL_DESCRIPTION},
    )
    return channel


# ---------------------------------------------------------------- pruning


def prune_channel_history(*, cap: int = CHANNEL_HISTORY_CAP) -> int:
    """Delete every message beyond the newest ``cap`` in each channel; return the count."""
    ranked = ChannelMessage.objects.annotate(
        rank=Window(
            expression=RowNumber(),
            partition_by=[F("channel_id")],
            order_by=[F("created_at").desc(), F("pk").desc()],
        )
    )
    stale_ids = list(ranked.filter(rank__gt=cap).values_list("pk", flat=True))
    if not stale_ids:
        return 0
    ChannelMessage.objects.filter(pk__in=stale_ids).delete()
    return len(stale_ids)
