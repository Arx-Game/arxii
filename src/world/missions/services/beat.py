"""Mission → Story Beat seam (5b.3 — stub-record only).

Phase 5b.3 lands the cross-app data shape:
  * Beat.required_mission FK (authoring-time: a Beat may name a MissionTemplate it requires)
  * MissionInstance.source_beat FK (runtime: an instance may have been launched as a Beat resolver)

The actual "complete the Beat when a mission terminates" engine is deferred. See:

  1. Which BeatOutcome does a mission completion produce? (Always SUCCESS? Per-route?)
  2. How does Beat.required_mission interact with BeatPredicateType? (Override?
     Constrained to GM_MARKED? New MISSION_COMPLETED predicate type?)
  3. How does (instance, beat) resolve to the right StoryProgress/GroupStoryProgress
     given the beat's StoryScope? (Holder's progress? All participants? GMTable lookup?)

These belong to a future stories-missions seam design pass. Until then,
on_mission_complete_for_beat() is a stub-record (appends to a module-level list,
same shape as integrations/beat_stub.py). Tests assert the trigger is recorded;
no BeatCompletion is created in 5b.3.

See docs/plans/2026-05-18-missions-design.md §13.x for the broader design intent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils import timezone

from world.missions.types import MissionBeatTriggerRecord

if TYPE_CHECKING:
    from world.missions.models import MissionInstance


_MISSION_BEAT_TRIGGERS: list[MissionBeatTriggerRecord] = []


def on_mission_complete_for_beat(
    instance: MissionInstance,
) -> MissionBeatTriggerRecord | None:
    """Record a Mission → Beat terminal trigger (5b.3 stub-record).

    Called from ``_finish_terminal`` after the instance is marked COMPLETE.

    * If ``instance.source_beat_id is None`` the instance is a free run
      (no Beat reporting). Returns ``None`` and records nothing — the call
      is a cheap no-op (one attribute read + return).
    * Otherwise: appends one :class:`MissionBeatTriggerRecord` to the
      module-level log and returns it. NOT idempotent — calling twice
      records two rows; mirrors the shape of
      :mod:`world.missions.integrations.beat_stub`.

    Phase 5b.3 deliberately does NOT create a
    :class:`world.stories.models.BeatCompletion` and does NOT call any
    stories service. The seam is data-only in 5b.3; see the module docstring
    for the three deferred product-level questions.
    """
    if instance.source_beat_id is None:
        return None
    record = MissionBeatTriggerRecord(
        instance_pk=instance.pk,
        beat_pk=instance.source_beat_id,
        triggered_at=timezone.now(),
    )
    _MISSION_BEAT_TRIGGERS.append(record)
    return record


def get_triggers() -> tuple[MissionBeatTriggerRecord, ...]:
    """An immutable snapshot of the recorded triggers (tuple, not list)."""
    return tuple(_MISSION_BEAT_TRIGGERS)


def clear_triggers() -> None:
    """Empty the recorded-trigger log (call in ``setUp`` for isolation)."""
    _MISSION_BEAT_TRIGGERS.clear()
