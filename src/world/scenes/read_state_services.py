"""Read-state services for the narrative play reader (#3759).

Private, cross-device read tracking — distinct from `reaction_toggle_services`'
toggle semantics (favorite/reaction: delete-if-present-else-create). Marking a
pose read is idempotent-create only: reading something twice is not "un-reading"
it.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from django.db.models import QuerySet
from django.utils import timezone
from django.utils.dateparse import parse_datetime

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

MAX_POSES_PER_BATCH = 100


class ReadBatchAuthorizationError(ValueError):
    """Raised when any explicit read reference is not canonical and visible."""


# Bulk mark-all-before-snapshot dismissal (#3759 spec section 7: "Separate
# explicit mark-all-before-snapshot operation for deliberate dismissal.").
# The caller (`play_views.PlayReadView`) has already bounded the DB read with
# a `timestamp <= before` filter pushed into the authorized queryset before
# this module ever sees a row, so this cap only protects the write side: a
# 5000-row `bulk_create(ignore_conflicts=True)` is a single cheap statement,
# and a realistic conversation backlog (even "returning after a long break")
# is nowhere near this in the alpha game. If a caller's authorized backlog
# somehow exceeds it, the newest (most likely still-unread) rows win — see
# `mark_conversation_read` — and the call is idempotent, so a second click
# picks up whatever the cap left behind.
MAX_CONVERSATION_MARK_READ = 5000


def _parse_timestamp(value: str) -> datetime:
    """Parse a canonical client timestamp, rejecting naive values."""
    parsed = parse_datetime(value)
    if parsed is None or not timezone.is_aware(parsed):
        raise ReadBatchAuthorizationError
    return parsed


def authorize_read_pairs(
    *, queryset: QuerySet, poses: list[tuple[int, str]]
) -> list[tuple[int, str]]:
    """Authorize every explicit ``(interaction_id, timestamp)`` independently.

    ``queryset`` must be the canonical viewer-visible interaction queryset. The
    returned list preserves the request's spelling for receipt creation, while
    comparison is by parsed instant. Any invalid, stale, hidden, deleted, or
    timestamp-mismatched pair rejects the entire batch.
    """
    if not poses:
        return []
    requested = []
    for pose_id, timestamp in poses:
        try:
            requested.append((int(pose_id), str(timestamp), _parse_timestamp(str(timestamp))))
        except (TypeError, ValueError, OverflowError):
            raise ReadBatchAuthorizationError from None
    ids = {pose_id for pose_id, _timestamp, _parsed in requested}
    visible = {
        (int(pose_id), timestamp)
        for pose_id, timestamp in queryset.filter(id__in=ids).values_list("id", "timestamp")
    }
    if any((pose_id, parsed) not in visible for pose_id, _timestamp, parsed in requested):
        raise ReadBatchAuthorizationError
    return [(pose_id, timestamp) for pose_id, timestamp, _parsed in requested]


def _mark_read_pairs(*, account: AccountDB, poses: list[tuple[int, str]]) -> int:
    """Idempotently record ``account`` having read each canonical pair."""
    from world.scenes.models import InteractionReadReceipt  # noqa: PLC0415

    parsed_pairs = {(pose_id, _parse_timestamp(timestamp)) for pose_id, timestamp in poses}
    if not parsed_pairs:
        return 0
    existing = set(
        InteractionReadReceipt.objects.filter(
            account=account,
            interaction_id__in=[pose_id for pose_id, _timestamp in parsed_pairs],
        ).values_list("interaction_id", "timestamp")
    )
    to_create = [
        InteractionReadReceipt(interaction_id=pose_id, timestamp=timestamp, account=account)
        for pose_id, timestamp in parsed_pairs
        if (pose_id, timestamp) not in existing
    ]
    if not to_create:
        return 0
    InteractionReadReceipt.objects.bulk_create(to_create, ignore_conflicts=True)
    return len(to_create)


def mark_poses_read(
    *,
    account: AccountDB,
    poses: list[tuple[int, str]],
) -> int:
    """Idempotently record `account` having read each `(interaction_id, timestamp)` pair.

    Returns the number of NEW receipts created (already-read poses are silently
    skipped, not errors). Caps at `MAX_POSES_PER_BATCH` — callers must page larger
    batches themselves.
    """
    return _mark_read_pairs(account=account, poses=poses[:MAX_POSES_PER_BATCH])


def mark_conversation_read(
    *,
    account: AccountDB,
    poses: list[tuple[int, str]],
) -> int:
    """Bulk mark-all-before-snapshot dismissal (#3759 spec section 7).

    `poses` must already be the caller's own authorized-and-filtered
    `(interaction_id, timestamp)` pairs for one conversation, bounded to
    `timestamp <= before` — `play_views.PlayReadView` builds this list via
    the same `_rows()`/`_queryset()` authorization path every other play view
    uses, never a raw `Interaction.objects.filter(...)`. Idempotent, like
    `mark_poses_read`: an already-read pose is silently skipped, not an
    error, so a repeat call (or a second click) is harmless.

    Capped at `MAX_CONVERSATION_MARK_READ`, keeping the *newest* poses when
    over cap (`poses[-N:]`) — those are the ones most likely still unread;
    older poses in a long history are more likely already read from natural
    forward scrolling.
    """
    if len(poses) > MAX_CONVERSATION_MARK_READ:
        poses = poses[-MAX_CONVERSATION_MARK_READ:]
    return _mark_read_pairs(account=account, poses=poses)


def has_read_pairs(
    *, account: AccountDB, poses: list[tuple[int, datetime]]
) -> set[tuple[int, datetime]]:
    """Return exact canonical pairs already marked read for ``account``."""
    from world.scenes.models import InteractionReadReceipt  # noqa: PLC0415

    ids = [pose_id for pose_id, _timestamp in poses]
    if not ids:
        return set()
    requested = {(pose_id, timestamp) for pose_id, timestamp in poses}
    existing = InteractionReadReceipt.objects.filter(
        account=account, interaction_id__in=ids
    ).values_list("interaction_id", "timestamp")
    return {
        (pose_id, timestamp) for pose_id, timestamp in existing if (pose_id, timestamp) in requested
    }


def has_read(*, account: AccountDB, interaction_ids: list[int]) -> set[int]:
    """Return IDs with any receipt (legacy helper for non-timestamp callers)."""
    from world.scenes.models import InteractionReadReceipt  # noqa: PLC0415

    return set(
        InteractionReadReceipt.objects.filter(
            account=account, interaction_id__in=interaction_ids
        ).values_list("interaction_id", flat=True)
    )
