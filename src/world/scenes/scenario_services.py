"""Scene scenario read (#3565) - the party's node and the GM's ballots.

Composed read only - no writes, no new models. Mirrors #3434's story-rail
pattern (see ``rail_services.py``): a single ``build_scene_scenario_payload``
gates its own sub-sections per-viewer. A scene may be running a mission
scenario (``MissionInstance`` with ``source_beat=scene.running_beat``,
started by ``start_scenario_for_scene``/``RunBeatAction``); this composes
the party's current group beat (participants only, the same shape as
``journal/{id}/group-beat/``) alongside a GM-only summary (current node,
every participant's ballot, the last resolved deed, the running beat's
outcome) for staff or viewers with standing on the running story.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from world.missions.constants import MissionStatus
from world.missions.models import MissionGroupBallot, MissionInstance, MissionParticipant
from world.missions.services.play import PHASE_PICK, PHASE_VOTE, group_beat as group_beat_service
from world.missions.types import GroupBallotState
from world.scenes.rail_services import viewer_has_story_standing

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB

    from world.scenes.models import Scene


def _running_instance(scene: Scene) -> MissionInstance | None:
    """The ACTIVE run this scene is currently playing out, or None.

    ``source_beat`` is set once (at ``start_scenario_for_scene``/
    ``gm_assign_mission``) and never repointed, so at most one ACTIVE
    instance exists per beat.
    """
    if scene.running_beat_id is None:
        return None
    return MissionInstance.objects.filter(
        source_beat_id=scene.running_beat_id, status=MissionStatus.ACTIVE
    ).first()


def _viewer_character(scene: Scene, user: AccountDB) -> ObjectDB | None:
    """The ObjectDB character the viewing account plays in this scene's party.

    Walks ``scene.persona_handler.active_participant_personas()`` (already
    scene-scoped) and returns the first persona's character whose owning
    account is ``user`` - via
    ``character_sheet.roster_entry_or_none.current_tenure.player_data.account``,
    the same ownership chain ``CharacterSheet.decay_tier`` walks. None when the
    viewer has no active character among this scene's participants (e.g. a GM
    who is not playing a PC here).
    """
    for persona in scene.persona_handler.active_participant_personas():
        sheet = persona.character_sheet
        entry = sheet.roster_entry_or_none
        tenure = entry.current_tenure if entry is not None else None
        if tenure is not None and tenure.player_data.account_id == user.pk:
            return sheet.character
    return None


def _last_deed_payload(instance: MissionInstance) -> dict[str, Any] | None:
    """The most recently applied deed on this run, as ``{option_key, outcome_name}``."""
    deed = instance.deeds.order_by("-applied_at").first()
    if deed is None:
        return None
    return {
        "option_key": deed.option.key,
        "outcome_name": deed.outcome.name if deed.outcome_id is not None else None,
    }


def _gm_ballots(instance: MissionInstance) -> tuple[GroupBallotState, ...]:
    node = instance.current_node
    if node is None:
        return ()
    ballots = MissionGroupBallot.objects.filter(instance=instance, node=node).select_related(
        "participant", "participant__character"
    )
    return tuple(
        GroupBallotState(
            character_id=ballot.participant.character_id,
            character_name=ballot.participant.character.character.db_key,
            picked_option_id=ballot.picked_option_id,
            voted_option_id=ballot.voted_option_id,
        )
        for ballot in ballots.order_by("participant__pk")
    )


def _gm_payload(scene: Scene, instance: MissionInstance) -> dict[str, Any]:
    """The GM-only scenario view: current node, every ballot, the last deed."""
    node = instance.current_node
    ballots = _gm_ballots(instance)
    n_active = instance.participants.count()
    phase = PHASE_VOTE if (n_active > 0 and len(ballots) >= n_active) else PHASE_PICK
    beat = scene.running_beat
    return {
        "node_key": node.key if node is not None else "",
        "flavor_text": node.flavor_text if node is not None else "",
        "conflict_mode": node.conflict_mode if node is not None else "",
        "phase": phase,
        "is_paused": instance.is_paused,
        "ballots": ballots,
        "last_deed": _last_deed_payload(instance),
        "beat_outcome": beat.outcome if beat is not None else "",
        "beat_outcome_key": beat.outcome_key if beat is not None else "",
    }


def build_scene_scenario_payload(scene: Scene, user: AccountDB) -> dict[str, Any]:
    """Compose the scenario payload for ``user`` viewing ``scene`` (#3565).

    ``instance_id`` is null when the scene runs no scenario. ``group_beat``
    is populated only when the viewer plays a participant on the run
    (never for a bystander or a GM with no PC here). ``gm`` is populated
    only for staff or viewers with standing on the running story
    (``viewer_has_story_standing``) - the same leak invariant #3434's story
    rail enforces.
    """
    instance = _running_instance(scene)
    payload: dict[str, Any] = {
        "instance_id": instance.pk if instance is not None else None,
        "is_paused": instance.is_paused if instance is not None else False,
        "viewer_is_participant": False,
        "group_beat": None,
        "gm": None,
    }
    if instance is None:
        return payload

    character = _viewer_character(scene, user)
    if (
        character is not None
        and MissionParticipant.objects.filter(instance=instance, character_id=character.pk).exists()
    ):
        payload["viewer_is_participant"] = True
        payload["group_beat"] = group_beat_service(instance, character)

    beat = scene.running_beat
    if beat is not None and viewer_has_story_standing(user, beat.episode.chapter.story):
        payload["gm"] = _gm_payload(scene, instance)

    return payload
