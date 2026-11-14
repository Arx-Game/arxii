"""Resolving the resonance a player picks to pay for each pulled thread (#5123)."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import TYPE_CHECKING

from world.magic.exceptions import PullValidationError
from world.magic.models import CharacterResonance

if TYPE_CHECKING:
    from world.magic.models import Resonance


def resolve_pull_payers(
    owner_sheet_id: int,
    thread_ids: Collection[int],
    payer_ids: Mapping[int, int] | None,
) -> dict[int, Resonance]:
    """Resolve a ``thread id -> resonance id`` map into resonances the owner holds.

    A thread left out of the map is paid by its leading resonance. A named resonance need
    not have a row on its thread (the character holds it, so it pays; it brings no perks).

    Raises:
        PullValidationError: A key that is not a pulled thread, or a resonance the
            character does not hold.
    """
    if not payer_ids:
        return {}
    wanted = {int(thread_id): int(res_id) for thread_id, res_id in payer_ids.items()}
    if not set(wanted) <= set(thread_ids):
        msg = "A payer was named for a thread that is not in the pull."
        raise PullValidationError(msg)
    held = {
        row.resonance_id: row.resonance
        for row in CharacterResonance.objects.filter(
            character_sheet_id=owner_sheet_id, resonance_id__in=set(wanted.values())
        ).select_related("resonance")
    }
    if not set(wanted.values()) <= set(held):
        msg = "A thread can only be paid by a resonance you hold."
        raise PullValidationError(msg)
    return {thread_id: held[res_id] for thread_id, res_id in wanted.items()}
