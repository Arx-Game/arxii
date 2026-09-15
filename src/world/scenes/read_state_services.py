"""Read-state services for the narrative play reader (#3759).

Private, cross-device read tracking — distinct from `reaction_toggle_services`'
toggle semantics (favorite/reaction: delete-if-present-else-create). Marking a
pose read is idempotent-create only: reading something twice is not "un-reading"
it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils.dateparse import parse_datetime

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

MAX_POSES_PER_BATCH = 100
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


def _mark_read_pairs(*, account: AccountDB, poses: list[tuple[int, str]]) -> int:
    """Idempotently record `account` having read each `(interaction_id, timestamp)` pair.

    Returns the number of NEW receipts created (already-read poses are silently
    skipped, not errors). Shared core for both the per-pose batch path
    (`mark_poses_read`) and the bulk conversation-dismissal path
    (`mark_conversation_read`) — callers own their own size cap.
    """
    from world.scenes.models import InteractionReadReceipt  # noqa: PLC0415

    existing = set(
        InteractionReadReceipt.objects.filter(
            account=account,
            interaction_id__in=[pose_id for pose_id, _ in poses],
        ).values_list("interaction_id", "timestamp")
    )
    to_create = []
    for pose_id, timestamp_str in poses:
        parsed = parse_datetime(timestamp_str)
        if parsed is None:
            continue
        if (pose_id, parsed) in existing:
            continue
        to_create.append(
            InteractionReadReceipt(interaction_id=pose_id, timestamp=parsed, account=account)
        )
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


def has_read(*, account: AccountDB, interaction_ids: list[int]) -> set[int]:
    """Return the subset of `interaction_ids` this account has already marked read."""
    from world.scenes.models import InteractionReadReceipt  # noqa: PLC0415

    return set(
        InteractionReadReceipt.objects.filter(
            account=account, interaction_id__in=interaction_ids
        ).values_list("interaction_id", flat=True)
    )
