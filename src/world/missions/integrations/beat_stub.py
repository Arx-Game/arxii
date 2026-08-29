"""In-memory stub for ``DeedRewardSink.BEAT`` reward-line deliveries only.

This file is NOT the Mission→Beat completion engine — that engine is live
(#1757): ``MissionInstance.source_beat`` + ``on_mission_complete_for_beat()``
(``world.missions.services.beat``) complete the linked ``Beat`` when a run
reaches its terminal node, called from ``_finish_terminal``
(``services/resolution.py``) and covered by ``test_services_beat.py``/
``test_services_resolution_beat.py``. That instance-level seam fires
independently of anything in this module.

What THIS module stubs is narrower: ``DeedRewardSink.BEAT`` reward lines are
reserved for future fine-grained per-deed Beat propagation (e.g. multi-beat
fan-out from a single mission's deeds) — deliberately deferred, not part of
#1757's scope. A BEAT-sink reward line is currently a no-op record; this stub
records the call in-memory so the apply-router test suite can verify it
fired, without doing anything with it yet.
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
