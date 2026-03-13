"""Task registry for the game clock scheduler."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import logging

from django.utils import timezone

from world.game_clock.models import ScheduledTaskRecord

logger = logging.getLogger("world.game_clock.scheduler")


class FrequencyType(Enum):
    REAL = "real"
    IC = "ic"


@dataclass(frozen=True)
class CronDefinition:
    task_key: str
    callable: Callable[[], None]
    interval: timedelta
    frequency_type: FrequencyType = FrequencyType.REAL
    description: str = ""


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

    Returns list of task_keys that were executed.
    """
    now = timezone.now()
    executed: list[str] = []

    for task_def in _registry:
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
