"""Services for assigning persisted interactions to anchored narrative threads."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from evennia.accounts.models import AccountDB

from world.scenes.constants import InteractionMode
from world.scenes.models import Interaction, InteractionThread
from world.scenes.place_models import InteractionReceiver, Place


class InteractionThreadError(ValueError):
    """A reply target cannot be used without exposing why to the caller.

    ``venue_hint`` is set only when the refusal is specifically the reachability
    rule (#3787 decision 3, "you can only answer someone in a venue where they
    are available") - a holder mismatch between the reply's own draft context
    and the target's. Other refusals (a missing or invisible target, a bad
    timestamp) leave it ``None``; there is nowhere to send the player.
    """

    code = "reply_target_unavailable"

    def __init__(
        self,
        message: str = "Cannot reply to that interaction.",
        *,
        venue_hint: str | None = None,
    ) -> None:
        super().__init__(message)
        # The player-facing sentence, held explicitly so a view never has to
        # serialise the exception itself. `str(exc)` on an exception is how a
        # stack trace or a database message reaches a response body by
        # accident (CodeQL py/stack-trace-exposure, and the "never str(exc) in
        # responses" standard in django_notes.md).
        self.detail = message
        self.venue_hint = venue_hint


@dataclass(frozen=True)
class ReplyTarget:
    """The serializer-level reference used to select an interaction thread."""

    interaction_id: int
    timestamp: datetime


def coerce_reply_target(value: object) -> ReplyTarget | None:
    """Normalize a REST or action-command reply target."""
    if value is None:
        return None
    if isinstance(value, ReplyTarget):
        return value
    if not isinstance(value, dict) or set(value) != {"id", "timestamp"}:
        raise _unavailable()
    try:
        interaction_id = int(value["id"])
        timestamp_value = value["timestamp"]
    except (TypeError, ValueError):
        raise _unavailable() from None
    if interaction_id < 1:
        raise _unavailable()
    if isinstance(timestamp_value, datetime):
        timestamp = timestamp_value
    elif isinstance(timestamp_value, str):
        timestamp = parse_datetime(timestamp_value)
    else:
        timestamp = None
    if timestamp is None or not timezone.is_aware(timestamp):
        raise _unavailable()
    return ReplyTarget(interaction_id=interaction_id, timestamp=timestamp)


@dataclass(frozen=True)
class HolderSignature:
    """Persisted holder identity used to keep a thread in one context."""

    kind: str
    holder_id: int | None = None
    room_id: int | None = None
    scene_id: int | None = None
    party_key: str | None = None

    def as_thread_kwargs(self) -> dict[str, object]:
        """Return fields suitable for creating an ``InteractionThread``."""
        return {
            "holder_kind": self.kind,
            "holder_id": self.holder_id,
            "room_id": self.room_id,
            "scene_id": self.scene_id,
            "party_key": self.party_key,
        }


def _unavailable(
    message: str = "Cannot reply to that interaction.",
    *,
    venue_hint: str | None = None,
) -> InteractionThreadError:
    return InteractionThreadError(message, venue_hint=venue_hint)


def _holder_mismatch(
    interaction: Interaction,
    interaction_signature: HolderSignature,
    target_signature: HolderSignature,
) -> InteractionThreadError:
    """Refuse a reply whose own venue cannot reach the target's (#3787 decision 3).

    Reachability is never widened to fit (decision 2 rejects audience
    promotion) - the caller must physically leave the venue that scopes their
    draft. The only wording specified by the approved demo (Screen 3) is this
    concrete direction: a Place-held draft (a table-talk aside) answering a
    Scene-held target (a room-wide pose, or a combat OUTCOME). Other holder
    mismatches keep the generic refusal - there is no ratified copy for them yet.
    """
    if (
        interaction_signature.kind == InteractionThread.HolderKind.PLACE
        and target_signature.kind == InteractionThread.HolderKind.SCENE
    ):
        place_name = interaction.place.name if interaction.place_id is not None else "this place"
        return _unavailable(
            "Answering the fight means speaking to the room.",
            venue_hint=f"Leave {place_name} to answer this. Your draft is kept.",
        )
    return _unavailable()


def _account_party(interaction: Interaction) -> tuple[int, ...]:
    """Return the pinned account party for a receiver-scoped interaction."""
    receiver_account_ids = tuple(
        sorted(
            account_id
            for account_id in InteractionReceiver.objects.filter(
                interaction_id=interaction.pk,
                timestamp=interaction.timestamp,
            ).values_list("account_id", flat=True)
            if account_id is not None
        )
    )
    if (
        interaction.writer_account_id is None
        or len(receiver_account_ids)
        != InteractionReceiver.objects.filter(
            interaction_id=interaction.pk,
            timestamp=interaction.timestamp,
        )
        .exclude(account_id__isnull=True)
        .count()
    ):
        raise _unavailable()
    return tuple(sorted((interaction.writer_account_id, *receiver_account_ids)))


def holder_signature(interaction: Interaction) -> HolderSignature:
    """Return the holder identity that can safely contain an interaction."""
    if interaction.mode == InteractionMode.WHISPER:
        party = _account_party(interaction)
        return HolderSignature(
            kind=InteractionThread.HolderKind.WHISPER, party_key=",".join(map(str, party))
        )

    if interaction.place_id is not None:
        try:
            room_id = Place.objects.values_list("room_id", flat=True).get(pk=interaction.place_id)
        except Place.DoesNotExist:
            raise _unavailable() from None
        if room_id is None:
            raise _unavailable()
        return HolderSignature(
            kind=InteractionThread.HolderKind.PLACE,
            holder_id=interaction.place_id,
            room_id=room_id,
            scene_id=interaction.scene_id,
        )

    if interaction.scene_id is not None:
        return HolderSignature(
            kind=InteractionThread.HolderKind.SCENE,
            holder_id=interaction.scene_id,
            scene_id=interaction.scene_id,
        )

    raise _unavailable()


def _receiver_accounts(interaction: Interaction) -> tuple[int, ...]:
    """Return the pinned receiver-account set for audience-preserving replies."""
    rows = InteractionReceiver.objects.filter(
        interaction_id=interaction.pk,
        timestamp=interaction.timestamp,
    )
    account_ids = tuple(sorted(rows.values_list("account_id", flat=True)))
    if any(account_id is None for account_id in account_ids):
        raise _unavailable()
    return account_ids


def _same_holder(thread: InteractionThread, signature: HolderSignature) -> bool:
    return (
        thread.holder_kind == signature.kind
        and thread.holder_id == signature.holder_id
        and thread.room_id == signature.room_id
        and thread.scene_id == signature.scene_id
        and thread.party_key == signature.party_key
    )


def _thread_anchored_at(
    target: Interaction,
    signature: HolderSignature,
) -> InteractionThread:
    """Find or create the thread that answers ``target`` (#3787).

    One thread per answered row, so two people answering the same blow land in the
    same exchange rather than each carrying their own copy of "I answered that".
    The anchor is the (id, timestamp) pair the partitioned interaction table needs;
    the holder fields come from the target, so a pre-existing thread's holder always
    matches - the check stays as a guard against a thread built for another venue.

    Nesting: when the target is ITSELF a reply it already belongs to a thread, which
    becomes this one's ``parent``; ``root`` is that thread's own root, or the parent
    when the parent is the top. Written as ids so neither hop costs a query.

    The find-or-create takes no lock of its own and does not need one: the caller
    already holds ``select_for_update`` on ``target``, and every reply to that row
    contends on it, so two answers to the same blow cannot both miss here and race to
    create. ``unique_thread_per_anchor`` is the backstop if that ever stops holding.
    """
    thread = InteractionThread.objects.filter(
        anchor_interaction_id=target.pk,
        anchor_timestamp=target.timestamp,
    ).first()
    if thread is not None:
        if not _same_holder(thread, signature):
            raise _unavailable()
        return thread

    parent_thread = target.thread
    parent_id = None if parent_thread is None else parent_thread.pk
    root_id = None if parent_thread is None else (parent_thread.root_id or parent_thread.pk)
    return InteractionThread.objects.create(
        anchor_interaction_id=target.pk,
        anchor_timestamp=target.timestamp,
        parent_id=parent_id,
        root_id=root_id,
        **signature.as_thread_kwargs(),
    )


def assign_interaction_thread(
    *,
    interaction: Interaction,
    reply_target: ReplyTarget,
    account_id: int | None,
) -> InteractionThread:
    """Put an interaction in the thread anchored at its reply target (#3787).

    The caller must invoke this while the interaction write is atomic. The target is
    locked before its visibility, holder, and existing thread are used.

    The target itself is NOT moved into the thread: a thread now holds the answers to
    one row, and that row is reachable as ``anchor_interaction``. So a reply's
    ``thread`` says what it answered, and a root pose keeps a null one.

    Returns the thread it assigned. ``create_interaction`` discards it - the thread is
    already on ``interaction`` by then - but the telnet and test callers that drive
    this service directly assert on it, so it is the return value rather than None.
    """
    if account_id is None or not timezone.is_aware(reply_target.timestamp):
        raise _unavailable()

    try:
        account = AccountDB.objects.get(pk=account_id)
    except AccountDB.DoesNotExist:
        raise _unavailable() from None

    target_queryset = (
        Interaction.objects.visible_to(account)
        .filter(pk=reply_target.interaction_id, timestamp=reply_target.timestamp)
        .select_for_update()
    )
    try:
        target = target_queryset.get()
    except Interaction.DoesNotExist:
        raise _unavailable() from None

    if target.timestamp >= interaction.timestamp:
        raise _unavailable()

    target_signature = holder_signature(target)
    interaction_signature = holder_signature(interaction)
    if target_signature != interaction_signature:
        raise _holder_mismatch(interaction, interaction_signature, target_signature)

    if target.place_id is not None and _receiver_accounts(target) != _receiver_accounts(
        interaction
    ):
        raise _unavailable()
    if target.mode == InteractionMode.WHISPER and _account_party(target) != _account_party(
        interaction
    ):
        raise _unavailable()

    thread = _thread_anchored_at(target, target_signature)
    interaction.thread = thread
    interaction.save(update_fields=["thread"])
    return thread
