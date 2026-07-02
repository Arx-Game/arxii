"""Combat encounter → story beat auto-wiring (#1746).

Wires the ENCOUNTER_COMPLETED reactive event to record_outcome_tier_completion:
when a CombatEncounter completes, classify_battle_outcome maps its
(EncounterOutcome, RiskLevel) to a designer-tunable CheckOutcome, and the
ENCOUNTER_COMPLETED subscriber resolves any linked OUTCOME_TIER beat via
record_outcome_tier_completion.

FLED/ABANDONED encounters (or any unmapped outcome×risk pair) resolve the beat
to PENDING_GM_REVIEW via force_outcome — a machine-detected non-success/failure
terminal outcome that needs a GM's adjudication rather than an immediate
pre-authored consequence.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from world.traits.models import CheckOutcome

if TYPE_CHECKING:
    from collections.abc import Sequence

    from world.character_sheets.models import CharacterSheet
    from world.combat.models import CombatEncounter
    from world.scenes.models import Scene
    from world.stories.models import Beat

logger = logging.getLogger(__name__)

ENCOUNTER_BEAT_TRIGGER_NAME = "encounter_completed_beat_wiring"


def staked_unsatisfied_beats_for_scene(scene: Scene) -> list[Beat]:
    """Staked, still-open beats on episodes linked to this scene (#1770 PR4).

    A beat is staked when its declared risk is above NONE; only UNSATISFIED
    beats can still be wagered on. Uses the same Scene -> EpisodeScene ->
    Episode -> Beat discovery as ``encounter_completed_beat_handler`` but
    without its OUTCOME_TIER restriction — any predicate type can carry a
    stakes contract.
    """
    from world.societies.constants import RenownRisk  # noqa: PLC0415
    from world.stories.constants import BeatOutcome  # noqa: PLC0415
    from world.stories.models import Beat, EpisodeScene  # noqa: PLC0415

    episode_ids = EpisodeScene.objects.filter(scene=scene).values_list("episode_id", flat=True)
    return list(
        Beat.objects.filter(
            episode_id__in=episode_ids,
            outcome=BeatOutcome.UNSATISFIED,
        ).exclude(risk=RenownRisk.NONE)
    )


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
        if not report.allowed:
            logger.info(
                "Stakes contract on beat %s not activated: blocked by a player boundary.",
                beat.pk,
            )
            continue
        activate_stakes_contract(beat, participant_sheets)


def classify_battle_outcome(encounter: CombatEncounter) -> CheckOutcome | None:
    """Map a completed encounter's (outcome, risk_level) to a CheckOutcome tier.

    Returns the designer-authored CheckOutcome for the encounter's outcome×risk,
    or None when no mapping row exists or the row's check_outcome is null
    (FLED/ABANDONED, or a pair the designers left unmapped). None signals the
    caller to resolve the beat to PENDING_GM_REVIEW rather than firing a
    consequence pool.

    Args:
        encounter: A completed CombatEncounter. Its ``outcome`` and
            ``risk_level`` drive the mapping lookup.

    Returns:
        The mapped CheckOutcome, or None.

    Raises:
        ValueError: if the encounter has no outcome set (programmer error — the
            ENCOUNTER_COMPLETED event only fires post-completion).
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

    mapping = EncounterOutcomeMapping.objects.filter(
        outcome=encounter.outcome,
        risk_level=encounter.risk_level,
    ).first()
    return mapping.check_outcome if mapping is not None else None


def encounter_completed_beat_handler(*, payload: object) -> None:
    """Flow-callable subscriber for ENCOUNTER_COMPLETED (#1746).

    Resolves any linked OUTCOME_TIER beat on the encounter's scene's episode(s):
    classifies the outcome and completes the beat via
    record_outcome_tier_completion. No-ops cleanly when the encounter has no
    scene, no linked beat, or no active progress. FLED/ABANDONED (or any unmapped
    outcome×risk) resolve the beat to PENDING_GM_REVIEW — a machine-detected
    non-success/failure terminal outcome held for a GM's adjudication.

    Dispatched by a system-installed Trigger (seeded via
    install_encounter_beat_trigger) bound to the seeded
    ``encounter_completed_beat_wiring`` TriggerDefinition.
    """
    import logging  # noqa: PLC0415

    from world.stories.constants import BeatOutcome, BeatPredicateType  # noqa: PLC0415
    from world.stories.models import Beat, EpisodeScene  # noqa: PLC0415
    from world.stories.services.beats import record_outcome_tier_completion  # noqa: PLC0415
    from world.stories.services.progress import (  # noqa: PLC0415
        get_active_progress_for_story,
    )

    logger = logging.getLogger(__name__)

    scene = payload.scene
    if scene is None:
        return

    encounter = payload.encounter
    # Find UNSATISFIED OUTCOME_TIER beats on episodes linked to this scene.
    episode_ids = EpisodeScene.objects.filter(scene=scene).values_list("episode_id", flat=True)
    beats = list(
        Beat.objects.filter(
            episode_id__in=episode_ids,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
            outcome=BeatOutcome.UNSATISFIED,
        )
    )
    if not beats:
        return

    outcome_tier = classify_battle_outcome(encounter)

    for beat in beats:
        progress = get_active_progress_for_story(beat.episode.chapter.story)
        if progress is None:
            logger.debug(
                "ENCOUNTER_COMPLETED: beat %s — no active progress for story; skipping.",
                beat.pk,
            )
            continue
        if outcome_tier is None:
            record_outcome_tier_completion(
                progress=progress,
                beat=beat,
                force_outcome=BeatOutcome.PENDING_GM_REVIEW,
            )
        else:
            record_outcome_tier_completion(
                progress=progress,
                beat=beat,
                outcome_tier=outcome_tier,
            )


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
        handler = getattr(room, "trigger_handler", None)  # noqa: GETATTR_LITERAL
        if handler is not None:
            handler.on_trigger_added(trigger)


def wire_encounter_beat_triggers() -> None:
    """Seed the ENCOUNTER_COMPLETED → beat TriggerDefinition (idempotent).

    Creates (get_or_create) the ``encounter_completed_beat_wiring`` FlowDefinition
    (one CALL_SERVICE_FUNCTION step → encounter_completed_beat_handler) and its
    TriggerDefinition. Doubles as integration-test setup and staff seed content.
    Safe to call repeatedly.
    """
    from world.combat.factories import (  # noqa: PLC0415
        EncounterBeatTriggerDefinitionFactory,
    )

    EncounterBeatTriggerDefinitionFactory()
