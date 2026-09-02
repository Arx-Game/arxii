"""Combat encounter -> story beat / scenario-option auto-wiring (#1746, #3565).

Wires the ENCOUNTER_COMPLETED reactive event to one of two grading targets,
mutually exclusive per encounter:

* A scenario ENCOUNTER option (``encounter.scenario_deed`` set, #3565): the
  fight grades its option's route on the mission scenario graph, never a
  story beat - ``world.missions.services.encounter_option.
  complete_encounter_for_option`` classifies and routes it, and FLED/
  ABANDONED are mapped tiers there like any other, authored the same as
  VICTORY/DEFEAT.
* A story beat (no ``scenario_deed``): beat_for_scene_conclusion (#3559)
  picks the single beat it may grade - the encounter's own explicitly routed
  story_beat, or the scene's running beat when it is itself the objective
  (kind ENCOUNTER) - classify_battle_outcome maps the encounter's
  (EncounterOutcome, RiskLevel) to a designer-tunable CheckOutcome, and
  record_outcome_tier_completion resolves it. FLED/ABANDONED never grade a
  beat here: the party walked away from the wager, so the beat stays
  UNSATISFIED and resolve_stakes_for_withdrawal fires each open stake's
  authored WITHDRAWAL branch instead.

Either way, an outcome x risk pair with no authored EncounterOutcomeMapping
row is missing content, not a pause - it is logged as an error (surfaced on
the admin sentinel, #3444) and the beat/run is left open/paused.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from world.stories.services.stakes import staked_unsatisfied_beats_for_scene
from world.traits.models import CheckOutcome

if TYPE_CHECKING:
    from collections.abc import Sequence

    from world.character_sheets.models import CharacterSheet
    from world.combat.models import CombatEncounter
    from world.scenes.models import Persona, Scene

logger = logging.getLogger(__name__)

ENCOUNTER_BEAT_TRIGGER_NAME = "encounter_completed_beat_wiring"


def activate_stakes_for_scene(
    scene: Scene | None,
    participant_sheets: Sequence[CharacterSheet],
) -> None:
    """Lock any staked beats' contracts for this scene's combat party (#1770 PR4).

    Called from the combat encounter-creation seams (``create_pvp_duel``,
    ``create_lethal_duel``, ``seed_or_feed_encounter_from_cast``) — combat
    entry is the commit moment (pillar 9). ``activate_stakes_contract`` is
    idempotent while an activation is open, so two encounters sharing a
    scene are safe. Boundary screen first (pillar 10): a blocked contract is
    skipped and logged privately — the reason is never surfaced to the GM
    or players (ADR-0033).
    """
    from world.stories.services.boundaries import check_stake_boundaries  # noqa: PLC0415
    from world.stories.services.stakes import activate_stakes_contract  # noqa: PLC0415

    if scene is None or not participant_sheets:
        return
    for beat in staked_unsatisfied_beats_for_scene(scene):
        report = check_stake_boundaries(beat.stakes.all(), participant_sheets)
        if not report.cleared:
            logger.info(
                "Stakes contract on beat %s not activated: blocked or awaiting "
                "sign-off on a player boundary.",
                beat.pk,
            )
            continue
        activate_stakes_contract(beat, participant_sheets)


def classify_battle_outcome(encounter: CombatEncounter) -> CheckOutcome:
    """Map a completed encounter's (outcome, risk_level) to a CheckOutcome tier.

    Args:
        encounter: A completed CombatEncounter. Its ``outcome`` and
            ``risk_level`` drive the mapping lookup.

    Returns:
        The designer-authored CheckOutcome for the encounter's outcome x risk.

    Raises:
        ValueError: if the encounter has no outcome set (programmer error - the
            ENCOUNTER_COMPLETED event only fires post-completion).
        EncounterOutcomeMapping.DoesNotExist: no row is authored for this
            outcome x risk pair. Missing content, not a data flag the caller
            branches on - see encounter_completed_beat_handler.
    """
    if not encounter.outcome:
        msg = (
            f"Encounter {encounter.pk} has no outcome; classify_battle_outcome "
            "should only be called on a completed encounter."
        )
        raise ValueError(msg)
    # Local import to avoid a circular dependency at module load: the factories
    # module imports ENCOUNTER_BEAT_TRIGGER_NAME from here (see Task 4).
    from world.combat.models import EncounterOutcomeMapping  # noqa: PLC0415

    mapping = EncounterOutcomeMapping.objects.get(
        outcome=encounter.outcome,
        risk_level=encounter.risk_level,
    )
    return mapping.check_outcome


def _participant_personas(encounter: CombatEncounter) -> list[Persona]:
    """Primary personas of this encounter's ACTIVE participants (#3559).

    Sheet -> primary_persona is the same mapping activate_stakes_for_scene's
    own callers already derive for stake activation.
    """
    from world.combat.constants import ParticipantStatus  # noqa: PLC0415

    sheets = [
        p.character_sheet for p in encounter.participants.filter(status=ParticipantStatus.ACTIVE)
    ]
    return [sheet.primary_persona for sheet in sheets]


def encounter_completed_beat_handler(*, payload: object) -> None:
    """Flow-callable subscriber for ENCOUNTER_COMPLETED (#1746, routed #1760).

    Grades at most ONE thing per completed encounter: a scenario ENCOUNTER
    option's route when ``encounter.scenario_deed`` is set (#3565 - delegates
    to ``encounter_option.complete_encounter_for_option`` and returns; never
    also grades a beat), otherwise a story beat via
    beat_for_scene_conclusion (#3559): the encounter's own explicitly routed
    ``story_beat``, or the scene's running beat when that beat is itself the
    objective (kind ENCOUNTER). Anything else - no linked beat, or one that
    isn't gradable - leaves the story untouched.

    FLED/ABANDONED encounters never grade a story beat: the party walked
    away from the wager, so resolve_stakes_for_withdrawal fires each open
    stake's authored WITHDRAWAL branch and the beat stays UNSATISFIED. (A
    scenario ENCOUNTER option's FLED/ABANDONED tiers are graded like any
    other - see ``encounter_option`` above.) Any other outcome classifies
    via classify_battle_outcome and completes through
    record_outcome_tier_completion; a missing EncounterOutcomeMapping row is
    content, not a pause - it is logged as an error (surfaced on the admin
    sentinel, #3444) and the beat is left open.

    Dispatched by a system-installed Trigger (seeded via
    install_encounter_beat_trigger) bound to the seeded
    ``encounter_completed_beat_wiring`` TriggerDefinition.
    """
    from world.combat.constants import EncounterOutcome  # noqa: PLC0415
    from world.combat.models import EncounterOutcomeMapping  # noqa: PLC0415
    from world.stories.services.beats import (  # noqa: PLC0415
        beat_for_scene_conclusion,
        record_outcome_tier_completion,
    )
    from world.stories.services.progress import (  # noqa: PLC0415
        get_active_progress_for_story,
    )
    from world.stories.services.stake_resolution import (  # noqa: PLC0415
        resolve_stakes_for_withdrawal,
    )

    scene = payload.scene
    if scene is None:
        return

    encounter = payload.encounter
    if encounter.scenario_deed_id is not None:
        from world.missions.services.encounter_option import (  # noqa: PLC0415
            complete_encounter_for_option,
        )

        complete_encounter_for_option(encounter)
        return

    beat = beat_for_scene_conclusion(scene, encounter.story_beat)
    if beat is None:
        return

    progress = get_active_progress_for_story(beat.episode.chapter.story)
    if progress is None:
        logger.debug(
            "ENCOUNTER_COMPLETED: beat %s - no active progress for story; skipping.",
            beat.pk,
        )
        return

    if encounter.outcome in (EncounterOutcome.FLED, EncounterOutcome.ABANDONED):
        resolve_stakes_for_withdrawal(beat, progress, _participant_personas(encounter))
        return

    try:
        tier = classify_battle_outcome(encounter)
    except EncounterOutcomeMapping.DoesNotExist:
        logger.exception(
            "No EncounterOutcomeMapping for outcome=%s risk=%s; beat %s left open "
            "(required content, see the admin sentinel).",
            encounter.outcome,
            encounter.risk_level,
            beat.pk,
        )
        return

    record_outcome_tier_completion(progress=progress, beat=beat, outcome_tier=tier)


def install_encounter_beat_trigger(encounter: CombatEncounter) -> None:
    """Idempotently install the beat-wiring Trigger on the encounter's room.

    Mirrors install_escalation_room_triggers: a system-installed Trigger
    (source_condition=None) bound to the seeded
    ``encounter_completed_beat_wiring`` TriggerDefinition. No-ops when the
    seeded definition is absent (content not wired in this deployment) or the
    encounter has no room.
    """
    from flows.models import Trigger, TriggerDefinition  # noqa: PLC0415

    room = encounter.room
    if room is None:
        return
    trigger_def = TriggerDefinition.objects.filter(name=ENCOUNTER_BEAT_TRIGGER_NAME).first()
    if trigger_def is None:
        return
    trigger, created = Trigger.objects.get_or_create(obj=room, trigger_definition=trigger_def)
    if created:
        handler = room.trigger_handler
        if handler is not None:
            handler.on_trigger_added(trigger)


def wire_encounter_beat_triggers() -> None:
    """Seed the ENCOUNTER_COMPLETED → beat TriggerDefinition (idempotent).

    Looks up the ``encounter_completed_beat_wiring`` FlowDefinition (one
    CALL_SERVICE_FUNCTION step → encounter_completed_beat_handler) and its
    TriggerDefinition. Doubles as integration-test setup and staff seed content.
    Safe to call repeatedly.

    ``flows.FlowDefinition``/``FlowStepDefinition``/``TriggerDefinition`` are
    all content-repo-owned (#2698) — looked up rather than invented unless
    ``SEED_SAMPLE_CONTENT`` is on. No-ops when the FlowDefinition isn't
    authored — ``install_encounter_beat_trigger`` already tolerates a missing
    TriggerDefinition.
    """
    from flows.models import TriggerDefinition  # noqa: PLC0415
    from world.combat.factories import _build_encounter_beat_flow  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415

    flow = _build_encounter_beat_flow()
    if flow is None:
        return
    authored_or_sample(
        TriggerDefinition,
        {
            "event_name": "encounter_completed",
            "flow_definition": flow,
            "priority": 40,
            "base_filter_condition": None,
        },
        name=ENCOUNTER_BEAT_TRIGGER_NAME,
    )
