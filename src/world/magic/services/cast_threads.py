"""Compute applicable threads for an out-of-combat technique cast (#768).

Passive tier-0 in-scope threads (via the canonical ``_anchor_in_action``
predicate) plus an optional declared paid pull, merged charge-free into the
``ApplicableThread`` list consumed by ``thread_power_term``. Charging of a
declared pull happens later, inside ``use_technique``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.magic.models import Thread
from world.magic.services.power_terms import ApplicableThread
from world.magic.services.resonance import _anchor_in_action
from world.magic.types.pull import PullActionContext

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import Technique
    from world.magic.types.pull import CastPullDeclaration


def build_cast_applicable_threads(
    sheet: CharacterSheet,
    technique: Technique | None,
    *,
    location_id: int | None = None,
    cast_pull: CastPullDeclaration | None = None,
) -> list[ApplicableThread]:
    """Return merged ApplicableThreads (passive tier-0 + declared pull). Charge-free."""
    ctx = PullActionContext(
        combat_encounter=None,
        involved_techniques=(technique.pk,) if technique is not None else (),
        involved_objects=(location_id,) if location_id is not None else (),
    )
    by_thread: dict[int, int] = {}
    threads = list(
        Thread.objects.filter(owner=sheet, retired_at__isnull=True).select_related(
            "resonance", "target_technique"
        )
    )
    for thread in threads:
        if _anchor_in_action(thread, ctx):
            by_thread[thread.pk] = 0
    resolved_threads = {t.pk: t for t in threads}
    if cast_pull is not None:
        for thread in cast_pull.threads:
            resolved_threads[thread.pk] = thread
            by_thread[thread.pk] = max(by_thread.get(thread.pk, 0), cast_pull.tier)
    return [
        ApplicableThread(thread=resolved_threads[pk], pull_tier=tier)
        for pk, tier in sorted(by_thread.items())
    ]
