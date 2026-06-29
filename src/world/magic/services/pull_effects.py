"""Gift-aware ThreadPullEffect resolver.

Single-thread resolution helper used by the pull pipeline and passive-bonus
handlers. For GIFT threads the resolver implements a two-step preference:
  1. Return rows whose ``target_gift`` matches the thread's gift.
  2. Fall back to ``target_gift IS NULL`` rows if no gift-specific row exists.

For all other target_kinds ``target_gift__isnull=True`` is enforced so that
gift-specific rows never leak into covenant/sanctum/facet/mantle paths.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.magic.constants import TargetKind
from world.magic.models import ThreadPullEffect

if TYPE_CHECKING:
    pass


def get_pull_effects_for_thread(thread: object, **filters: object) -> list[ThreadPullEffect]:
    """Return ThreadPullEffect rows for ``thread`` with gift-specific preference.

    For ``TargetKind.GIFT`` threads:
      - Tries rows where ``target_gift == thread.target_gift`` first.
      - Falls back to ``target_gift IS NULL`` when no gift-specific row exists.

    For all other target_kinds:
      - Returns only ``target_gift IS NULL`` rows (covenant/sanctum behavior
        is byte-identical to the pre-#1580 state).

    Args:
        thread: A Thread instance (must expose ``target_kind``, ``resonance``,
            and—for GIFT kind—``target_gift``).
        **filters: Additional ORM filter kwargs forwarded to the query
            (e.g. ``tier=0``, ``effect_kind=EffectKind.FLAT_BONUS``,
            ``min_thread_level__lte=t.level``).

    Returns:
        A list (possibly empty) of matching ThreadPullEffect rows.
    """
    base_qs = ThreadPullEffect.objects.filter(
        target_kind=thread.target_kind,
        resonance=thread.resonance,
        **filters,
    )
    if thread.target_kind == TargetKind.GIFT:
        gift_rows = list(base_qs.filter(target_gift=thread.target_gift))
        if gift_rows:
            return gift_rows
        return list(base_qs.filter(target_gift__isnull=True))
    return list(base_qs.filter(target_gift__isnull=True))
