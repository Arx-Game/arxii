"""The offscreen-act gate (#3412) — governs "2.5 acts".

A character in a degraded lifecycle state (captured, unconscious, unknown
whereabouts, retired, dead) cannot be onscreen, but a narrow set of actions —
journal entries, character goals, persona swaps, proclamations — represent
things the *player* can still do offscreen on the character's behalf. This
module is the single predicate that decides what those acts resolve to for a
given character right now.

``offscreen_act_state()`` is pure and side-effect free: one field read
(``sheet.lifecycle_state``, already loaded on the instance — no query) plus
at most one cheap query (``world.vitals.services.unconscious_instance``).
No writes, no queries in loops.

Binding precedence (see EPHEMERAL-PLAN-3412-S3/task-1-brief.md): DEAD beats
unconscious beats CAPTURED beats UNKNOWN/RETIRED beats ALIVE. This mirrors
``world.vitals.services.perceives_dreamside`` — death always wins over a
lingering Unconscious instance. Action keys outside ``OFFSCREEN_ACT_KEYS``
always resolve ALLOWED without inspecting lifecycle state at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from actions.constants import (
    OFFSCREEN_ACT_KEYS,
    OFFSCREEN_CHANNEL_DREAM,
    OFFSCREEN_LIFECYCLE_DISPOSITIONS,
    OFFSCREEN_REASON_DEAD,
    OFFSCREEN_REASON_UNCONSCIOUS,
    OffscreenActState,
)

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet


@dataclass(frozen=True)
class OffscreenGateResult:
    """Result of an offscreen-act gate check.

    Attributes:
        state: ALLOWED / ROUTED / BLOCKED (see ``OffscreenActState``).
        channel: Names how word could still travel for a ROUTED disposition
            (e.g. ``OFFSCREEN_CHANNEL_SMUGGLE``, ``OFFSCREEN_CHANNEL_DREAM``).
            None for ALLOWED and BLOCKED.
        reason: PLACEHOLDER world-voice text told to the actor — non-empty
            for ROUTED and BLOCKED, None for ALLOWED.
    """

    state: OffscreenActState
    channel: str | None = None
    reason: str | None = None


_ALLOWED_RESULT = OffscreenGateResult(state=OffscreenActState.ALLOWED)


def offscreen_act_state(sheet: CharacterSheet | None, action_key: str) -> OffscreenGateResult:
    """Return the offscreen-act disposition for *sheet* attempting *action_key*.

    Pure — no side effects, no writes. Any ``action_key`` not in
    ``OFFSCREEN_ACT_KEYS`` (and a ``None`` sheet) always resolves ALLOWED
    without inspecting lifecycle state at all.
    """
    if sheet is None or action_key not in OFFSCREEN_ACT_KEYS:
        return _ALLOWED_RESULT

    from world.character_sheets.types import LifecycleState  # noqa: PLC0415
    from world.vitals.services import unconscious_instance  # noqa: PLC0415

    # DEAD wins over everything, including a lingering Unconscious instance
    # (mirrors perceives_dreamside — a ghost watches, it does not dream).
    if sheet.lifecycle_state == LifecycleState.DEAD:
        return OffscreenGateResult(state=OffscreenActState.BLOCKED, reason=OFFSCREEN_REASON_DEAD)

    # Unconscious is an overlay independent of lifecycle_state — it beats
    # CAPTURED/UNKNOWN/RETIRED/ALIVE alike.
    if unconscious_instance(sheet) is not None:
        return OffscreenGateResult(
            state=OffscreenActState.ROUTED,
            channel=OFFSCREEN_CHANNEL_DREAM,
            reason=OFFSCREEN_REASON_UNCONSCIOUS,
        )

    disposition = OFFSCREEN_LIFECYCLE_DISPOSITIONS.get(sheet.lifecycle_state)
    if disposition is None:
        # ALIVE, and the unwritten COMA member — neither is keyed on.
        return _ALLOWED_RESULT
    state, channel, reason = disposition
    return OffscreenGateResult(state=state, channel=channel, reason=reason)
