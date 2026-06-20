"""Block resolution + lifecycle (#1278, slice 1).

The coded enforcement primitive the rest of the system will call: "is there an active block
between these two (player, persona) sides?" Block is mutual — it hides each side from the other —
and keyed on PlayerData (account), so it follows the *person* across re-rosters.

Slice 1 is resolution + lifecycle only; wiring it into the profile gate, scene visibility, the
target picker, the awareness/flag layer, and the cron job are follow-up slices.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Q
from django.utils import timezone

from world.scenes.models import Block

if TYPE_CHECKING:
    from datetime import datetime

    from evennia_extensions.models import PlayerData
    from world.scenes.models import Persona


def coded_block_active(
    *,
    player_a: PlayerData,
    persona_a: Persona | None,
    player_b: PlayerData,
    persona_b: Persona | None,
) -> bool:
    """True if an active coded block sits between these two (player, persona) sides (#1278).

    Symmetric: a block hides each side from the other, so the order of the arguments does not
    matter. A block matches when the **exact blocked persona** is involved (the default
    persona→persona case) or, for an ``account_level`` block, when any of the blocker's faces
    meets the blocked persona. Keyed on PlayerData, so a character now played by a *different*
    person does not match (the block follows the original player).

    This is the coded-enforcement check only. The blocked player's *other* identities are handled
    by the separate awareness/flag layer (a later slice) — never here, to preserve the
    anti-derivation invariant.
    """
    candidates = Block.objects.filter(
        Q(owner=player_a, blocked_player=player_b) | Q(owner=player_b, blocked_player=player_a)
    ).filter(Q(pending_removal_at__isnull=True) | Q(pending_removal_at__gt=timezone.now()))

    for block in candidates:
        # Orient the provided sides against this row: which one is the blocked player?
        if block.blocked_player_id == player_b.pk:
            blocked_face, blocker_face = persona_b, persona_a
        else:
            blocked_face, blocker_face = persona_a, persona_b

        # When the row names an exact blocked face, that face must be the one involved.
        if block.blocked_persona_id is not None and (
            blocked_face is None or blocked_face.pk != block.blocked_persona_id
        ):
            continue
        # The blocker's face must match too — unless the block covers all their characters.
        if (
            not block.account_level
            and block.blocker_persona_id is not None
            and (blocker_face is None or blocker_face.pk != block.blocker_persona_id)
        ):
            continue
        return True
    return False


def lift_block(block: Block, *, finalize_at: datetime) -> Block:
    """Begin lifting a block — it stays active until ``finalize_at`` (the next cron tick) (#1278).

    Deliberately delayed: an immediately-cleared block lets someone lift it, get a last word in,
    and re-block. ``finalize_expired_blocks`` removes it once the grace period elapses. Pass the
    timestamp in (the runtime forbids ``timezone.now()`` defaults in importable module code paths
    that must stay deterministic — callers compute the cron tick).
    """
    block.pending_removal_at = finalize_at
    block.save(update_fields=["pending_removal_at"])
    return block


def finalize_expired_blocks(*, now: datetime) -> int:
    """Delete blocks whose lift grace period has elapsed (cron entry point) (#1278).

    Returns the number removed. ``now`` is passed in so the caller (the cron job) controls the
    clock.
    """
    expired = Block.objects.filter(pending_removal_at__isnull=False, pending_removal_at__lte=now)
    count = expired.count()
    expired.delete()
    return count
