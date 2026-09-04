"""Scene clock services (#3567): the only writer of ``SceneClock`` rows.

A clock is keyed by beat (``running_beat_for_scene`` resolves which beat a
scene runs; a staged battle's private scene runs the same beat and shares the
clock). Ticks come from combat round starts and the GM ``advance_clock``
gesture. When the clock fills, the beat completes EXPIRED through
``complete_beat_expired`` in a ``transaction.on_commit`` callback, so the
completion runs in its own transaction after the caller's commit and a later
failure in a round pipeline can never roll back a completion players were
already told about (ADR-0264). Re-checked under a row lock, so a concurrent
SUCCESS completion or a double tick never completes a beat twice.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.scenes.beat_selectors import running_beat_for_scene
from world.scenes.constants import SceneClockClosedReason
from world.scenes.models import SceneClock
from world.stories.constants import BeatOutcome
from world.stories.models import Beat
from world.stories.services.beats import complete_beat_expired

if TYPE_CHECKING:
    from world.scenes.models import Scene

logger = logging.getLogger(__name__)


def open_clock_for_beat(beat: Beat) -> SceneClock | None:
    """The beat's open clock, or None."""
    return SceneClock.objects.filter(beat=beat, closed_at__isnull=True).first()


def start_scene_clock(scene: Scene, beat: Beat) -> SceneClock | None:
    """Open a clock of ``beat.clock_size`` in ``scene``; reuse an open one; None when 0."""
    if beat.clock_size <= 0:
        return None
    existing = open_clock_for_beat(beat)
    if existing is not None:
        return existing
    return SceneClock.objects.create(scene=scene, beat=beat, size=beat.clock_size)


def _complete_filled_clock_beat(beat_pk: int) -> None:
    """on_commit callback: lock the beat, complete EXPIRED if still open."""
    with transaction.atomic():
        beat = Beat.objects.select_for_update().get(pk=beat_pk)
        if beat.outcome != BeatOutcome.UNSATISFIED:
            logger.debug("Clock filled on beat %s already %s; skipping.", beat_pk, beat.outcome)
            return
        complete_beat_expired(beat)


@transaction.atomic
def tick_scene_clock(scene: Scene, *, by: int = 1) -> SceneClock | None:
    """Advance the running beat's open clock by ``by`` (never past full).

    Returns the clock after the tick, or None when the scene runs no beat or
    the beat has no open clock. Filling stamps ``closed_at``/FILLED and
    schedules the EXPIRED completion for after this transaction commits.
    """
    beat = running_beat_for_scene(scene)
    if beat is None:
        return None
    clock = SceneClock.objects.select_for_update().filter(beat=beat, closed_at__isnull=True).first()
    if clock is None:
        return None
    clock.filled = min(clock.size, clock.filled + max(by, 0))
    fields = ["filled"]
    if clock.filled >= clock.size:
        clock.closed_at = timezone.now()
        clock.closed_reason = SceneClockClosedReason.FILLED
        fields += ["closed_at", "closed_reason"]
        transaction.on_commit(lambda: _complete_filled_clock_beat(beat.pk))
    clock.save(update_fields=fields)
    return clock


def close_open_clock_for_beat(beat: Beat, reason: str) -> SceneClock | None:
    """Close the beat's open clock with ``reason``; None when there is none."""
    clock = open_clock_for_beat(beat)
    if clock is None:
        return None
    clock.closed_at = timezone.now()
    clock.closed_reason = reason
    clock.save(update_fields=["closed_at", "closed_reason"])
    return clock


def close_scene_clocks(scene: Scene, reason: str) -> int:
    """Close every open clock opened in ``scene``; returns the count closed."""
    count = 0
    for clock in SceneClock.objects.filter(scene=scene, closed_at__isnull=True):
        clock.closed_at = timezone.now()
        clock.closed_reason = reason
        clock.save(update_fields=["closed_at", "closed_reason"])
        count += 1
    return count
