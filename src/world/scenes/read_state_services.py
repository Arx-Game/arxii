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
    from world.scenes.models import InteractionReadReceipt  # noqa: PLC0415

    poses = poses[:MAX_POSES_PER_BATCH]
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


def has_read(*, account: AccountDB, interaction_ids: list[int]) -> set[int]:
    """Return the subset of `interaction_ids` this account has already marked read."""
    from world.scenes.models import InteractionReadReceipt  # noqa: PLC0415

    return set(
        InteractionReadReceipt.objects.filter(
            account=account, interaction_id__in=interaction_ids
        ).values_list("interaction_id", flat=True)
    )
