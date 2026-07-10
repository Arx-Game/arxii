"""Per-target-kind pull-effect modulation seam (#1831).

Dispatches on ``thread.target_kind``. COVENANT_ROLE empowers by the Court
leader's signed NpcRegard for the live target (#1831); RELATIONSHIP_TRACK
empowers by the owner's own bond strength to the thread's threaded person,
when the live target IS that person or is hostile toward them (#1849).
Returns ``base_scaled`` unchanged when there is no target, no rule, or the
rule declines to modulate — so all existing (untargeted or unrelated-kind)
pulls are byte-identical.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.magic.constants import TargetKind

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.magic.models import Thread, ThreadPullEffect


def apply_target_modulation(
    thread: Thread,
    target: ObjectDB | None,
    effect_row: ThreadPullEffect,
    base_scaled: int | None,
) -> int | None:
    """Modulate ``base_scaled`` for the live ``target``, or pass it through unchanged.

    No-op (returns ``base_scaled`` as-is) when there is no numeric payload, no
    target, or the thread's ``target_kind`` has no modulation rule.
    """
    if base_scaled is None:
        return base_scaled
    if target is None:
        return base_scaled
    if thread.target_kind == TargetKind.COVENANT_ROLE:
        from world.magic.services.pull_modulation_court import (  # noqa: PLC0415
            court_regard_modulation,
        )

        return court_regard_modulation(thread, target, effect_row, base_scaled)
    if thread.target_kind in (
        TargetKind.RELATIONSHIP_TRACK,
        TargetKind.RELATIONSHIP_CAPSTONE,
    ):
        from world.magic.services.pull_modulation_relationship import (  # noqa: PLC0415
            relationship_bond_modulation,
        )

        return relationship_bond_modulation(thread, target, effect_row, base_scaled)
    return base_scaled
