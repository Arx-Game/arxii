"""The writes of one clock jump, computed before anything is changed (#5248).

When staff set the game clock's date, ``set_clock`` moves the clock's anchors, the
scheduled tasks' in-game stamps, dying-window deadlines, upcoming events and, when ages
are kept, every character's birth year. Every one of those models is identity-mapped,
so a value assigned to an instance is live for the whole process at once, and a
rolled-back transaction does not take it back.

A ``JumpPlan`` therefore splits the work in two. ``set`` records one intended value and
changes nothing; the callers compute every new value this way first, so an
arithmetic failure (a date shifted past the calendar's ends) happens while nothing has
been touched. ``apply`` then assigns them all and writes them, and if the write fails it
puts every instance back as it was before raising.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from django.db import models

#: Why a jump may bulk-write identity-mapped rows: the instances written are the cached
#: ones, changed in place, so the identity map and the database agree afterwards.
_WRITE_REASON = "clock jump: cached instances changed in place, then written"


@dataclass(frozen=True)
class _PlannedWrite:
    instance: models.Model
    field: str
    value: Any
    previous: Any


class JumpPlan:
    """Every field one clock jump will change, held until ``apply``."""

    def __init__(self) -> None:
        self._writes: list[_PlannedWrite] = []

    def set(self, instance: models.Model, field: str, value: Any) -> None:
        """Record that ``instance.field`` becomes ``value``. Changes nothing yet."""
        self._writes.append(_PlannedWrite(instance, field, value, getattr(instance, field)))

    def __len__(self) -> int:
        return len(self._writes)

    def apply(self) -> None:
        """Assign every recorded value and write it; restore them all if a write fails."""
        if not self._writes:
            return
        for write in self._writes:
            setattr(write.instance, write.field, write.value)
        written = False
        try:
            grouped: dict[tuple[type[models.Model], str], list[models.Model]] = defaultdict(list)
            for write in self._writes:
                grouped[(type(write.instance), write.field)].append(write.instance)
            for (model, field), instances in grouped.items():
                model.objects.bulk_update_with_reason(instances, [field], reason=_WRITE_REASON)
            written = True
        finally:
            # Whatever stopped the write, the instances must not keep values the
            # database never took.
            if not written:
                for write in self._writes:
                    setattr(write.instance, write.field, write.previous)
