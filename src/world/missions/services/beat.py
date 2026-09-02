"""Mission → Story Beat seam.

When a ``MissionInstance`` with ``source_beat`` set reaches a terminal route,
``on_mission_complete_for_beat`` completes the linked ``Beat`` automatically.
``beat_outcome_for_route`` (#3560, #3565) decides what the run reports: the
terminal route's authored ``beat_outcome`` wins when set; otherwise a graded
route derives SUCCESS/FAILURE from the tier's ``success_level`` sign, and a
tier-less terminal (BRANCH, or ``route=None``) is SUCCESS - reaching a
terminal node means the party navigated the scenario to an ending. An
OUTCOME_TIER beat records that outcome (plus the graded tier, when there is
one) via ``record_scenario_outcome``; any other predicate type still routes
through ``record_gm_marked_outcome``. Either way, the option that ended the
run is threaded through as ``outcome_key`` so an authored
``TransitionRequiredOutcome.required_outcome_key`` downstream of the beat can
branch on which ending fired.

Free-run instances (``source_beat_id is None``) are a no-op, as before. The
trigger-record log (``MissionBeatTriggerRecord``) is retained for
observability.

The three deferred questions from the original 5b.3 stub are now resolved:

  1. Which ``BeatOutcome``: ``beat_outcome_for_route`` above.
  2. ``required_mission``/``predicate_type``: independent columns; the engine
     dispatches on ``beat.predicate_type``. Mismatches are logged, not
     raised. No new predicate type.
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
    from world.missions.models import MissionInstance, MissionOption, MissionOptionRoute
    from world.scenes.models import Persona
    from world.stories.constants import BeatOutcome
    from world.traits.models import CheckOutcome

logger = logging.getLogger(__name__)


_MISSION_BEAT_TRIGGERS: list[MissionBeatTriggerRecord] = []


def beat_outcome_for_route(
    route: MissionOptionRoute | None,
) -> tuple[BeatOutcome, CheckOutcome | None]:
    """What the linked beat records for a terminal route (#3560).

    Authored ``beat_outcome`` wins. Otherwise a graded route derives from the
    tier's success_level, and a tier-less terminal (BRANCH, or a terminal with
    no route row) is SUCCESS: the party navigated the scenario to an ending.
    """
    from world.stories.constants import BeatOutcome  # noqa: PLC0415

    tier = route.outcome_tier if route is not None and route.outcome_tier_id is not None else None
    if route is not None and route.beat_outcome:
        return BeatOutcome(route.beat_outcome), tier
    if tier is not None:
        return (BeatOutcome.SUCCESS if tier.success_level > 0 else BeatOutcome.FAILURE), tier
    return BeatOutcome.SUCCESS, None


def on_mission_complete_for_beat(
    instance: MissionInstance,
    *,
    route: MissionOptionRoute | None = None,
    option: MissionOption | None = None,
) -> MissionBeatTriggerRecord | None:
    """Record a Mission → Beat terminal trigger and complete the linked Beat.

    Called from ``_finish_terminal`` after the instance is marked COMPLETE.

    Args:
        instance: The terminating ``MissionInstance``.
        route: The terminal ``MissionOptionRoute`` (or ``None`` for a BRANCH
            terminal that has no route object). Feeds ``beat_outcome_for_route``.
        option: The ``MissionOption`` that ended the run. Its ``key`` is
            recorded as the beat completion's ``outcome_key`` (#3560) so an
            authored ``required_outcome_key`` transition downstream can route
            on which ending fired. ``None`` when no single option resolved
            the terminal (defensive only - every real terminal has one).

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
    _complete_linked_beat(instance, route, option)
    return record


def _run_personas(instance: MissionInstance) -> list[Persona]:
    """Primary personas of the run's participants, for GROUP-scope legend pools."""
    return [
        participant.character.primary_persona
        for participant in instance.participants.select_related("character")
    ]


def _complete_linked_beat(
    instance: MissionInstance,
    route: MissionOptionRoute | None,
    option: MissionOption | None,
) -> None:
    """Complete the instance's linked Beat via the stories service.

    Resolves ``StoryProgress`` from the beat's story chain, derives the
    ending via ``beat_outcome_for_route``, then dispatches:

      * OUTCOME_TIER beat → ``record_scenario_outcome`` (carries the graded
        tier, when there is one, plus ``option.key`` as ``outcome_key``).
      * any other predicate type → ``record_gm_marked_outcome`` (also carries
        ``outcome_key``; GM_MARKED beats still resolve through the GM's own
        manual call otherwise).

    Predicate-type mismatches and missing progress are logged and skipped —
    a beat-completion failure must never roll back the mission completion
    (the instance is already COMPLETE when this runs).
    """
    from world.stories.constants import BeatOutcome, BeatPredicateType  # noqa: PLC0415
    from world.stories.models import Beat  # noqa: PLC0415
    from world.stories.services.beats import (  # noqa: PLC0415
        record_gm_marked_outcome,
        record_scenario_outcome,
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

    outcome, tier = beat_outcome_for_route(route)
    key = option.key if option is not None else ""
    participants = _run_personas(instance)

    try:
        if beat.predicate_type == BeatPredicateType.OUTCOME_TIER:
            record_scenario_outcome(
                progress=progress,
                beat=beat,
                outcome=outcome,
                outcome_tier=tier,
                outcome_key=key,
                participants=participants,
            )
        else:
            record_gm_marked_outcome(
                progress=progress,
                beat=beat,
                outcome=outcome,
                outcome_key=key,
                participants=participants,
            )
    except ValueError:
        logger.warning(
            "MissionBeat: predicate-type mismatch for beat %s "
            "(type=%s, outcome=%s); skipping completion.",
            beat.pk,
            beat.predicate_type,
            outcome,
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
    if not report.cleared:
        logger.info(
            "Stakes contract on beat %s not activated for mission instance %s: "
            "blocked or awaiting sign-off on a player boundary.",
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
