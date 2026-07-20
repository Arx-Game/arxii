"""Task registry for the game clock scheduler."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum, IntEnum
import logging

from django.utils import timezone

from world.game_clock.models import ScheduledTaskRecord

logger = logging.getLogger("world.game_clock.scheduler")


class FrequencyType(Enum):
    REAL = "real"
    IC = "ic"


class CronPhase(IntEnum):
    """Execution-order bands for tasks that share a tick (#2609).

    Ordering used to be an emergent property of ``register_task`` call order —
    two lines hundreds apart in ``tasks.py``, with nothing saying the
    relationship was load-bearing. A phase states the intent at the call site.

    Bands are spaced so new ones can be inserted without renumbering. Tasks
    that do not care stay in ``DEFAULT``; sorting is stable, so within a band
    registration order still decides.

    The money bands encode the income-before-upkeep ruling (see
    ``docs/adr/0150-income-lands-before-upkeep.md``): a player experiences a
    smaller effective paycheck, never an unpreventable condition slide.
    """

    SNAPSHOT = 100  # pre-income baselines — read balances before anything moves
    ECONOMY = 200  # weekly_rollover: income, wages, debt service, contracts
    UPKEEP = 300  # building upkeep and personal recurring drains
    DEFAULT = 500  # everything with no ordering opinion
    CLEANUP = 900  # sweeps, decay, garbage collection


@dataclass(frozen=True)
class CronDefinition:
    task_key: str
    callable: Callable[[], None]
    interval: timedelta
    frequency_type: FrequencyType = FrequencyType.REAL
    description: str = ""
    # Optional weekly anchor (#932): when set, the task is due once the most
    # recent anchor moment (weekday at anchor_hour_utc) has passed since the
    # last run — instead of the rolling interval. 0=Monday … 6=Sunday.
    anchor_weekday: int | None = None
    anchor_hour_utc: int = 0
    # Execution-order band within a single run_due_tasks pass (#2609). This is
    # the ordering contract; registration order is only a tiebreak within a
    # band. Phases order tasks that are due *together* — a task must also share
    # an anchor with its neighbours for the ordering to ever come into play.
    phase: CronPhase = CronPhase.DEFAULT


# Module-level registry populated once at server startup via register_all_tasks().
# Not threadsafe for writes; safe for reads after startup completes.
_registry: list[CronDefinition] = []


def register_task(task: CronDefinition) -> None:
    """Register a periodic task (idempotent by task_key)."""
    if any(t.task_key == task.task_key for t in _registry):
        return
    _registry.append(task)


def get_registered_tasks() -> list[CronDefinition]:
    """Return all registered tasks."""
    return list(_registry)


def clear_registry() -> None:
    """Clear all registered tasks (for testing)."""
    _registry.clear()


def run_due_tasks(*, ic_now: datetime | None = None) -> list[str]:
    """Check all registered tasks and run any that are due.

    Tasks execute in ``CronPhase`` order (#2609). The sort is stable, so tasks
    sharing a phase keep registration order — the pre-#2609 behaviour for every
    task that has not opted into a band.

    Returns list of task_keys that were executed.
    """
    now = timezone.now()
    executed: list[str] = []

    for task_def in sorted(_registry, key=lambda task: task.phase):
        record, _ = ScheduledTaskRecord.objects.get_or_create(
            task_key=task_def.task_key,
        )
        if not record.enabled:
            continue

        if _is_task_due(record, task_def, now=now, ic_now=ic_now):
            try:
                task_def.callable()
                record.last_run_at = now
                if ic_now is not None:
                    record.last_ic_run_at = ic_now
                record.save(update_fields=["last_run_at", "last_ic_run_at"])
                executed.append(task_def.task_key)
                logger.info("Executed task: %s", task_def.task_key)
            except Exception:
                logger.exception("Task failed: %s", task_def.task_key)

    return executed


def _is_task_due(
    record: ScheduledTaskRecord,
    task_def: CronDefinition,
    *,
    now: datetime,
    ic_now: datetime | None,
) -> bool:
    """Check whether a task is due to run."""
    if task_def.anchor_weekday is not None:
        return _is_anchored_weekly_due(record, task_def, now=now)
    if task_def.frequency_type == FrequencyType.REAL:
        if record.last_run_at is None:
            return True
        return (now - record.last_run_at) >= task_def.interval

    # IC-frequency tasks
    if ic_now is None:
        return False
    if record.last_ic_run_at is None:
        return True
    return (ic_now - record.last_ic_run_at) >= task_def.interval


def _is_anchored_weekly_due(
    record: ScheduledTaskRecord,
    task_def: CronDefinition,
    *,
    now: datetime,
) -> bool:
    """Due once per weekly anchor (#932 — the Arx 1 Sunday-rollover feel).

    The anchor moment is ``anchor_weekday`` at ``anchor_hour_utc``. The task
    is due when the most recent anchor moment has passed and the last run
    predates it (first run fires on the next anchor — no surprise rollover
    the moment the task ships).
    """
    days_since_anchor = (now.weekday() - task_def.anchor_weekday) % 7
    last_anchor = (now - timedelta(days=days_since_anchor)).replace(
        hour=task_def.anchor_hour_utc, minute=0, second=0, microsecond=0
    )
    if last_anchor > now:
        last_anchor -= timedelta(days=7)
    if record.last_run_at is None:
        # Stamp a baseline so the first fire happens at the NEXT anchor.
        record.last_run_at = now
        record.save(update_fields=["last_run_at"])
        return False
    return record.last_run_at < last_anchor
