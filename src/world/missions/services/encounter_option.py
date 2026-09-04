"""ENCOUNTER options: a scenario node resolved by a combat encounter (#3565).

Objective-first (spec decision 10): the fight grades its option's route through
EncounterOutcomeMapping, never the story beat. The pick creates the pending
deed and the encounter, pauses the run, and the ENCOUNTER_COMPLETED handler
finishes the deed and routes it exactly like a rolled CHECK. FLED and
ABANDONED are tiers like any other here: their mapping rows are required
content (admin sentinel) and the GM authors their routes.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import transaction

from world.missions.constants import MissionStatus
from world.missions.models import MissionDeedRecord, MissionParticipant
from world.missions.services.resolution import _route_graded_outcome
from world.missions.types import PresentedOption
from world.narrative.constants import NarrativeCategory
from world.narrative.services import emit_ambient_room_stir, send_narrative_message

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.combat.models import CombatEncounter
    from world.missions.models import MissionInstance, MissionNode, MissionOption
    from world.scenes.models import Scene

logger = logging.getLogger(__name__)

_ERR_NO_SCENE = "There is no active scene for this fight."


def _scene_for_run(instance: MissionInstance, actor: MissionParticipant) -> Scene:
    """The scene running the run's beat, else the active scene where the actor stands."""
    from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415
    from world.scenes.models import Scene  # noqa: PLC0415

    if instance.source_beat_id is not None:
        scene = (
            Scene.objects.filter(running_beat_id=instance.source_beat_id, is_active=True)
            .order_by("-pk")
            .first()
        )
        if scene is not None:
            return scene
    scene = get_active_scene(actor.character.character.location)
    if scene is None:
        raise ValueError(_ERR_NO_SCENE)
    return scene


@transaction.atomic
def start_encounter_for_option(
    instance: MissionInstance,
    node: MissionNode,
    option: MissionOption,
    actor: MissionParticipant,
) -> MissionDeedRecord:
    """Pick an ENCOUNTER option: mint the pending deed + fight, pause the run.

    The deed is created with ``outcome=None`` (pending - the fight hasn't
    resolved yet) and linked to the new ``CombatEncounter`` via
    ``scenario_deed``, the one pointer the ENCOUNTER_COMPLETED handler needs
    to find its way back to this option pick. The run pauses
    (``is_paused=True``) for the duration of the fight -
    ``resolve_beat_option`` refuses further picks until it unpauses.
    """
    from world.combat.encounter_prep import spawn_opponent_lines  # noqa: PLC0415
    from world.combat.models import CombatEncounter  # noqa: PLC0415
    from world.combat.services import (  # noqa: PLC0415
        finalize_new_encounter,
        update_encounter_settings,
    )

    scene = _scene_for_run(instance, actor)
    deed = MissionDeedRecord.objects.create(
        instance=instance,
        actor=actor.character,
        node=node,
        option=option,
        outcome=None,
    )
    encounter = CombatEncounter.objects.create(scene=scene, scenario_deed=deed)
    finalize_new_encounter(encounter)
    update_encounter_settings(encounter, risk_level=option.encounter_risk_level)
    spawn_opponent_lines(
        encounter,
        option.opponent_lines.select_related("creature_template").order_by("order"),
    )
    instance.is_paused = True
    instance.save(update_fields=["is_paused"])
    return deed


def _narrate_encounter_resolution(
    instance: MissionInstance, deed: MissionDeedRecord, character: ObjectDB
) -> None:
    """STORY prose to every participant + a source-ambiguous ambient stir.

    Mirrors ``multiplayer._emit_group_resolution_narrative``: reuses
    ``play._story_text_for`` for the fired route's outcome_text (a fired
    candidate's override first, else the route's own) so the fight's
    completion narrates exactly like a rolled CHECK's resolution.
    """
    from world.missions.services.play import _story_text_for  # noqa: PLC0415

    presented = PresentedOption(
        option=deed.option,
        kind=deed.option.option_kind,
        check_type=None,
        base_risk=0,
        ic_framing=deed.option.authored_ic_framing,
        owner=character,
    )
    story_text = _story_text_for(presented, deed, instance.template.name)
    for participant in instance.participants.select_related("character"):
        send_narrative_message(
            recipients=[participant.character],
            body=story_text,
            category=NarrativeCategory.STORY,
            ooc_note=f"Mission encounter resolved (instance #{instance.pk}).",
        )
    anchor_room = instance.anchor_room
    if anchor_room is not None:
        emit_ambient_room_stir(anchor_room.objectdb)


def complete_encounter_for_option(encounter: CombatEncounter) -> MissionDeedRecord | None:
    """Grade the pending deed a completed ENCOUNTER fight resolves; unpause the run.

    Called from ``world.combat.beat_wiring.encounter_completed_beat_handler``
    when the completed encounter carries a ``scenario_deed`` - a scenario
    ENCOUNTER pick, never a story beat. Classifies the encounter's
    (outcome, risk_level) via ``classify_battle_outcome`` into a
    ``CheckOutcome`` tier and routes it through ``_route_graded_outcome``
    exactly like a rolled CHECK - FLED and ABANDONED are tiers like any
    other here, authored the same as VICTORY/DEFEAT.

    Returns ``None`` (and leaves the run paused) when the deed is already
    graded, the run isn't ACTIVE, or no ``EncounterOutcomeMapping`` row is
    authored for this (outcome, risk_level) pair - required content, never
    guarded around; the missing pair is logged (surfaced on the admin
    sentinel, #3444) and a GM must author the missing row before the run
    can continue.
    """
    from world.combat.beat_wiring import classify_battle_outcome  # noqa: PLC0415
    from world.combat.models import EncounterOutcomeMapping  # noqa: PLC0415

    deed = encounter.scenario_deed
    if deed is None or deed.outcome_id is not None:
        return None
    instance = deed.instance
    if instance.status != MissionStatus.ACTIVE:
        return None
    try:
        tier = classify_battle_outcome(encounter)
    except EncounterOutcomeMapping.DoesNotExist:
        logger.exception(
            "No EncounterOutcomeMapping for outcome=%s risk=%s; scenario run %s stays "
            "paused at node %s (required content, see the admin sentinel).",
            encounter.outcome,
            encounter.risk_level,
            instance.pk,
            deed.node_id,
        )
        return None
    instance.is_paused = False
    instance.save(update_fields=["is_paused"])
    actor = MissionParticipant.objects.get(instance=instance, character=deed.actor)
    character = actor.character.character
    deed = _route_graded_outcome(
        instance,
        deed.node,
        deed.option,
        character,
        tier,
        chosen_approach=None,
        advance=True,
        deed=deed,
    )
    _narrate_encounter_resolution(instance, deed, character)
    return deed
