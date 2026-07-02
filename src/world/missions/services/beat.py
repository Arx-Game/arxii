"""Mission → Story Beat seam.

When a ``MissionInstance`` with ``source_beat`` set reaches a terminal route,
``on_mission_complete_for_beat`` completes the linked ``Beat`` automatically:

  * A graded ``outcome_tier`` (CHECK/JOINT terminal) drives
    ``record_outcome_tier_completion`` (PR1), which derives
    ``BeatOutcome.SUCCESS``/``FAILURE`` from ``success_level`` and fires the
    beat's consequence pool at the matching tier.
  * A null ``outcome_tier`` (BRANCH terminal, or ``route=None``) drives
    ``record_gm_marked_outcome`` with ``SUCCESS`` — reaching a terminal branch
    node means the mission was navigated to completion.

Free-run instances (``source_beat_id is None``) are a no-op, as before. The
trigger-record log (``MissionBeatTriggerRecord``) is retained for
observability.

The three deferred questions from the original 5b.3 stub are now resolved:

  1. Which ``BeatOutcome``: derived from ``outcome_tier.success_level`` sign
     (graded) or ``SUCCESS`` (BRANCH), matching PR1's convention.
  2. ``required_mission``/``predicate_type``: independent columns; the engine
     dispatches on ``route.outcome_tier`` presence. Mismatches are logged,
     not raised. No new predicate type.
  3. ``StoryProgress`` scope: resolved via ``beat.episode.chapter.story`` →
     ``get_active_progress_for_story``. ``None`` (story not started) is a
     safe no-op.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.utils import timezone

from world.missions.types import MissionBeatTriggerRecord

if TYPE_CHECKING:
    from collections.abc import Sequence

    from world.character_sheets.models import CharacterSheet
    from world.missions.models import MissionInstance, MissionOptionRoute

logger = logging.getLogger(__name__)


_MISSION_BEAT_TRIGGERS: list[MissionBeatTriggerRecord] = []


def on_mission_complete_for_beat(
    instance: MissionInstance,
    *,
    route: MissionOptionRoute | None = None,
) -> MissionBeatTriggerRecord | None:
    """Record a Mission → Beat terminal trigger and complete the linked Beat.

    Called from ``_finish_terminal`` after the instance is marked COMPLETE.

    Args:
        instance: The terminating ``MissionInstance``.
        route: The terminal ``MissionOptionRoute`` (or ``None`` for a BRANCH
            terminal that has no route object). Its ``outcome_tier``
            determines which completion path fires.

    Returns:
        The recorded ``MissionBeatTriggerRecord``, or ``None`` when the
        instance is a free run (``source_beat_id is None``).
    """
    if instance.source_beat_id is None:
        return None
    record = MissionBeatTriggerRecord(
        instance_pk=instance.pk,
        beat_pk=instance.source_beat_id,
        triggered_at=timezone.now(),
    )
    _MISSION_BEAT_TRIGGERS.append(record)
    _complete_linked_beat(instance, route)
    return record


def _complete_linked_beat(
    instance: MissionInstance,
    route: MissionOptionRoute | None,
) -> None:
    """Complete the instance's linked Beat via the stories service.

    Resolves ``StoryProgress`` from the beat's story chain, then dispatches:

      * graded ``outcome_tier`` → ``record_outcome_tier_completion``
      * no tier (``route is None`` or ``route.outcome_tier is None``) →
        ``record_gm_marked_outcome(SUCCESS)``

    Predicate-type mismatches and missing progress are logged and skipped —
    a beat-completion failure must never roll back the mission completion
    (the instance is already COMPLETE when this runs).
    """
    from world.stories.constants import BeatOutcome  # noqa: PLC0415
    from world.stories.models import Beat  # noqa: PLC0415
    from world.stories.services.beats import (  # noqa: PLC0415
        record_gm_marked_outcome,
        record_outcome_tier_completion,
    )
    from world.stories.services.progress import (  # noqa: PLC0415
        get_active_progress_for_story,
    )

    try:
        beat = Beat.objects.select_related(
            "episode__chapter__story",
        ).get(pk=instance.source_beat_id)
    except Beat.DoesNotExist:
        logger.warning(
            "MissionBeat: source_beat %s not found for instance %s; skipping.",
            instance.source_beat_id,
            instance.pk,
        )
        return

    if beat.outcome != BeatOutcome.UNSATISFIED:
        logger.debug(
            "MissionBeat: beat %s already resolved (%s); skipping.",
            beat.pk,
            beat.outcome,
        )
        return

    story = beat.episode.chapter.story
    progress = get_active_progress_for_story(story)
    if progress is None:
        logger.debug(
            "MissionBeat: no active progress for story %s; skipping beat %s.",
            story.pk,
            beat.pk,
        )
        return

    has_tier = route is not None and route.outcome_tier_id is not None

    try:
        if has_tier:
            record_outcome_tier_completion(
                progress=progress,
                beat=beat,
                outcome_tier=route.outcome_tier,
            )
        else:
            record_gm_marked_outcome(
                progress=progress,
                beat=beat,
                outcome=BeatOutcome.SUCCESS,
            )
    except ValueError:
        logger.warning(
            "MissionBeat: predicate-type mismatch for beat %s "
            "(type=%s, has_tier=%s); skipping completion.",
            beat.pk,
            beat.predicate_type,
            has_tier,
        )


def activate_stakes_for_instance(
    instance: MissionInstance,
    participant_sheets: Sequence[CharacterSheet],
) -> None:
    """Lock a staked linked beat's contract at mission acceptance (#1770 PR4).

    Mission acceptance is the commit moment (pillar 9): when the run resolves
    a specific ``source_beat`` that carries a stakes contract, activate it
    for the accepting party. No-op for free runs (``source_beat`` null) and
    unstaked beats. Boundary screen first (pillar 10): a blocked contract is
    skipped and logged privately — the reason is never surfaced (ADR-0033).
    ``activate_stakes_contract`` is idempotent while an activation is open.
    """
    from world.societies.constants import RenownRisk  # noqa: PLC0415
    from world.stories.services.boundaries import check_stake_boundaries  # noqa: PLC0415
    from world.stories.services.stakes import activate_stakes_contract  # noqa: PLC0415

    if instance.source_beat_id is None or not participant_sheets:
        return
    beat = instance.source_beat
    if beat is None or beat.risk == RenownRisk.NONE:
        return
    report = check_stake_boundaries(beat.stakes.all(), participant_sheets)
    if not report.allowed:
        logger.info(
            "Stakes contract on beat %s not activated for mission instance %s: "
            "blocked by a player boundary.",
            beat.pk,
            instance.pk,
        )
        return
    activate_stakes_contract(beat, participant_sheets)


def get_triggers() -> tuple[MissionBeatTriggerRecord, ...]:
    """An immutable snapshot of the recorded triggers (tuple, not list)."""
    return tuple(_MISSION_BEAT_TRIGGERS)


def clear_triggers() -> None:
    """Empty the recorded-trigger log (call in ``setUp`` for isolation)."""
    _MISSION_BEAT_TRIGGERS.clear()
