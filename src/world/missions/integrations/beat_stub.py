"""In-memory beat-completion stub (Phase 5b.1 placeholder).

# DESIGN: Reward-line BEAT sinks (DeedRewardSink.BEAT) are reserved for future
# fine-grained Beat propagation (e.g., per-deed beat advancement, multi-beat
# fan-out). The PRIMARY Beat seam is MissionInstance.source_beat →
# on_mission_complete_for_beat() called at terminal (Phase 5b.3). A BEAT-sink
# reward line is currently a no-op record; the canonical instance-level seam
# fires independently when the mission terminates.

Phase 5b.3 landed the cross-app data shape (Beat.required_mission +
MissionInstance.source_beat FKs) and ``on_mission_complete_for_beat()`` as
the canonical instance-level seam; the real BeatCompletion engine is
deferred to a future stories-missions seam design pass. This stub's
behavior is unchanged: it records BEAT-sink line deliveries in-memory so
the apply-router test suite can verify the call fired.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.missions.integrations.types import BeatStubCall

if TYPE_CHECKING:
    from world.missions.models import MissionDeedRewardLine


_BEAT_CALLS: list[BeatStubCall] = []


def propagate_beat(line: MissionDeedRewardLine) -> None:
    """Record one BEAT-sink delivery call (Phase 5b.3 will replace this).

    Does NOT raise. BEAT lines can carry any kind (IMMEDIATE / POST_CRON /
    PROPAGATION) — the kind affects WHEN the line was emitted but not WHO
    receives the beat; the stub records the call unconditionally so 5b.3's
    real implementation gets the same trigger shape.
    """
    _BEAT_CALLS.append(
        BeatStubCall(
            line_id=line.pk,
            recipient_id=line.recipient_id,
            amount=line.amount,
            ref=line.ref,
        )
    )


def get_calls() -> tuple[BeatStubCall, ...]:
    """An immutable snapshot of the recorded calls (tuple, not list)."""
    return tuple(_BEAT_CALLS)


def clear_calls() -> None:
    """Empty the recorded-call log (call in ``setUp`` for isolation)."""
    _BEAT_CALLS.clear()
