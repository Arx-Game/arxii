"""Cron batch service for deferred reward payouts (Phase 5b.2).

Phase 5b.1 wrote :class:`MissionRewardQueue` rows for every POST_CRON
reward line. Phase 5b.2 is the *cron* that walks those queued rows and
grants the underlying reward downstream — except both grant entry points
are currently stub-sealed pending payload-enrichment work:

  * LEGEND_POINTS — the LP grant entry point requires richer line shape
    than the queue carries today (persona walk + LegendSourceType + title).
    See DESIGN §13.3.
  * RESONANCE — the resonance grant needs a Resonance FK and a
    ``MISSION_REWARD`` ``GainSource`` value that does not yet exist. Same
    DESIGN §13.3 reference.

Both helpers raise :class:`NotImplementedError` with a structured DESIGN
message; the batch catches the raise, populates ``failure_reason``, and
leaves the row at ``applied=False``. Future phases that enrich the queue
payload will replace the stub-seal body with real grant calls without
having to change the public batch contract.

Per-row :func:`transaction.atomic` keeps a fault on row N from corrupting
adjacent rows; idempotency is automatic in 5b.2 because no row ever flips
to ``applied=True``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.missions.constants import DeedRewardKind, DeedRewardSink
from world.missions.models import MissionRewardQueue
from world.missions.services.rewards import MissionRewardRoutingError
from world.missions.types import RewardBatchResult

if TYPE_CHECKING:
    pass


# Per-sink stub-seal messages. Both reference DESIGN §13.3 — the missions
# design doc section that explains why these grants need richer payloads
# than the queue carries today.
_LP_STUB_MSG = (
    "DESIGN §13.3 — LP grant entry point requires richer line shape: "
    "persona walk + LegendSourceType + title. Awaiting payload-enrichment phase."
)
_RESONANCE_STUB_MSG = (
    "DESIGN §13.3 — Resonance grant requires Resonance FK + MISSION_REWARD "
    "GainSource (does not exist). Awaiting payload-enrichment phase."
)

# MissionRewardQueue.failure_reason is a CharField(max_length=500); clip
# anything longer when we surface unexpected exceptions.
_FAILURE_REASON_MAX = 500


def _grant_legend_points(line: MissionRewardQueue) -> None:
    """Stub-sealed LP grant entry point.

    The canonical LP grant function expects a per-persona walk plus a
    :class:`LegendSourceType` (lookup) plus a title — none of which the
    queue row carries today. Until the payload-enrichment phase lands, this
    helper raises a structured NotImplementedError so the cron records a
    "tried but blocked" trace on the row rather than silently flipping
    ``applied=True``.
    """
    raise NotImplementedError(_LP_STUB_MSG)


def _grant_resonance(line: MissionRewardQueue) -> None:
    """Stub-sealed resonance grant entry point.

    The canonical resonance grant function expects a :class:`Resonance` FK
    plus a ``GainSource`` value (and ``GainSource.MISSION_REWARD`` is not
    in the enum yet — adding it prematurely would leak Phase-6 model
    surface area). Stub-sealed for the same reason as LP.
    """
    raise NotImplementedError(_RESONANCE_STUB_MSG)


def _apply_one(line: MissionRewardQueue) -> str | None:
    """Try to grant one queue row's reward downstream.

    Returns ``None`` on success (the row was flipped to ``applied=True``)
    or a non-empty failure-reason string when the grant raised. Per-row
    :func:`transaction.atomic` is wrapped by the caller, not here — so an
    inner write that succeeds before a later raise also rolls back inside
    the savepoint.
    """
    if line.kind == DeedRewardKind.POST_CRON and line.sink == DeedRewardSink.LEGEND_POINTS:
        _grant_legend_points(line)
    elif line.kind == DeedRewardKind.POST_CRON and line.sink == DeedRewardSink.RESONANCE:
        _grant_resonance(line)
    else:
        # Defensive: ``apply_deed_rewards`` only enqueues the two POST_CRON
        # sinks, so this arm should be unreachable. Raise a typed routing
        # error so the cron's catch-all records a clear failure_reason.
        raise MissionRewardRoutingError(
            kind=line.kind,
            sink=line.sink,
            line_pk=line.line_id,
        )

    # Success path (unreachable in 5b.2 — both helpers above raise).
    line.applied = True
    line.applied_at = timezone.now()
    line.failure_reason = ""
    line.save(update_fields=["applied", "applied_at", "failure_reason"])
    return None


def _record_failure(line: MissionRewardQueue, reason: str) -> None:
    """Persist a per-row failure reason without flipping ``applied``."""
    line.failure_reason = reason[:_FAILURE_REASON_MAX]
    line.save(update_fields=["failure_reason"])


def apply_mission_reward_batch() -> RewardBatchResult:
    """Walk every ``applied=False`` :class:`MissionRewardQueue` row and try to grant it.

    Each row is processed in its own savepoint (:func:`transaction.atomic`)
    so a fault on row N does not corrupt rows N-1 or N+1. In Phase 5b.2
    both ``_grant_legend_points`` and ``_grant_resonance`` raise
    :class:`NotImplementedError` with a DESIGN §13.3 message — the cron
    catches that, records the message on the row's ``failure_reason``, and
    leaves ``applied=False``. Idempotency falls out automatically: rerunning
    the batch touches the same set of rows and produces the same state.

    Returns:
        A typed :class:`RewardBatchResult` carrying the queue rows that
        succeeded (always empty in 5b.2) and the rows that failed (every
        unapplied row in 5b.2).
    """
    unapplied = list(
        MissionRewardQueue.objects.filter(applied=False)
        .select_related("line", "deed")
        .order_by("pk")
    )

    applied: list[MissionRewardQueue] = []
    failed: list[MissionRewardQueue] = []

    for row in unapplied:
        try:
            with transaction.atomic():
                outcome = _apply_one(row)
        except NotImplementedError as exc:
            _record_failure(row, str(exc))
            failed.append(row)
            continue
        except MissionRewardRoutingError as exc:
            _record_failure(row, exc.user_message)
            failed.append(row)
            continue
        except Exception as exc:  # noqa: BLE001 — cron must not crash on row faults
            _record_failure(row, f"{type(exc).__name__}: {exc}")
            failed.append(row)
            continue

        if outcome is None:
            applied.append(row)
        else:
            # Defensive path for the future: a helper that signals
            # soft-failure via a returned message rather than raising.
            _record_failure(row, outcome)
            failed.append(row)

    return RewardBatchResult(applied=tuple(applied), failed=tuple(failed))


__all__ = ("apply_mission_reward_batch",)
