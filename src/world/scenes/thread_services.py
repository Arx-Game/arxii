"""Services for assigning persisted interactions to flat narrative threads."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from django.utils import timezone
from evennia.accounts.models import AccountDB

from world.scenes.constants import InteractionMode
from world.scenes.models import Interaction, InteractionThread
from world.scenes.place_models import InteractionReceiver, Place


class InteractionThreadError(ValueError):
    """A reply target cannot be used without exposing why to the caller."""

    code = "reply_target_unavailable"


@dataclass(frozen=True)
class ReplyTarget:
    """The serializer-level reference used to select an interaction thread."""

    interaction_id: int
    timestamp: datetime


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


def _unavailable() -> InteractionThreadError:
    return InteractionThreadError("Cannot reply to that interaction.")


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


def assign_interaction_thread(
    *,
    interaction: Interaction,
    reply_target: ReplyTarget,
    account_id: int | None,
) -> InteractionThread:
    """Assign an interaction to the target's existing or newly-created thread.

    The caller must invoke this while the interaction write is atomic. The target
    is locked before its visibility, holder, and existing membership are used.
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
        raise _unavailable()

    if target.place_id is not None and _receiver_accounts(target) != _receiver_accounts(
        interaction
    ):
        raise _unavailable()
    if target.mode == InteractionMode.WHISPER and _account_party(target) != _account_party(
        interaction
    ):
        raise _unavailable()

    thread = target.thread
    if thread is None:
        thread = InteractionThread.objects.create(**target_signature.as_thread_kwargs())
        target.thread = thread
        target.save(update_fields=["thread"])
    elif not _same_holder(thread, target_signature):
        raise _unavailable()

    interaction.thread = thread
    interaction.save(update_fields=["thread"])
    return thread
