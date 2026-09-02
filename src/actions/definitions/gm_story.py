"""GM session-prep run actions (#3425).

A GM authors what a beat stages ahead of a session -- opponent lines
(``BeatOpponentLine``) for an ENCOUNTER beat, situation/challenge templates
(``BeatStagedTemplate``) for a SITUATION beat -- and, at the table, presses
"Run this beat" to instantiate all of it into the live scene at once:
``RunBeatAction``. ``GMListRunnableBeatsAction`` is the read side that feeds
the web "Run Beat" tab (and telnet, if a future command wants it) a scoped
list of ENCOUNTER/SITUATION beats on episodes the acting GM currently runs.

Deliberately a new module (not ``gm_stories.py``, which holds the story/beat
*lifecycle* actions -- complete/resolve/promote/mark/declare-stakes): this is
a run-time instantiation seam, closer in shape to ``gm_combat.py``'s
encounter-creation actions than to a beat lifecycle transition.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

from actions.base import Action
from actions.definitions.gm_stories import _actor_is_lead_gm
from actions.prerequisites import IsSceneGMPrerequisite, MinimumGMLevelPrerequisite, Prerequisite
from actions.types import ActionContext, ActionResult, TargetType
from commands.exceptions import CommandError
from commands.utils.gm_resolution import resolve_account_or_none, resolve_position_by_name
from world.gm.constants import GMLevel
from world.societies.constants import RenownRisk
from world.stories.constants import BeatKind
from world.stories.models import Beat
from world.stories.permissions import CanMarkBeat

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB

    from world.scenes.models import Scene

logger = logging.getLogger(__name__)

_NOT_RUNNABLE_KIND = "Only ENCOUNTER and SITUATION beats can be run into a scene."
_NO_BEAT = "A beat is required."
_NO_SUCH_BEAT = "No beat with that ID exists."
_NO_BEAT_PERMISSION = "You do not have authority over this beat's story."
_NO_ACTIVE_SCENE = "There is no active scene here."
_ALREADY_RUNNING_OTHER = "This scene is already running a different beat."

# Decision 3 (#3425 spec): RenownRisk -> combat RiskLevel, by name, with NONE
# folded into LOW (a beat authored at NONE risk still needs SOME encounter
# risk_level; MODERATE is combat's own default, so a beat that declared no
# stakes shouldn't inherit it). LETHAL is never auto-set -- GM-only, via the
# pre-existing UpdateEncounterSettingsAction control.
_RISK_MAP: dict[str, str] = {
    RenownRisk.NONE: "low",
    RenownRisk.LOW: "low",
    RenownRisk.MODERATE: "moderate",
    RenownRisk.HIGH: "high",
    RenownRisk.EXTREME: "extreme",
}

_RUNNABLE_KINDS = (BeatKind.ENCOUNTER, BeatKind.SITUATION)


def _actor_may_run_beat(account: AccountDB | None, beat: Beat) -> bool:
    """Whether *account* may run *beat* into a scene.

    Reuses ``CanMarkBeat.has_object_permission`` via a duck-typed request shim
    rather than re-deriving the Lead-GM/staff/approved-AGM chain a third time.
    ``BeatSerializer.get_can_mark`` is the precedent for calling this
    permission outside DRF -- it passes a real ``Request``; here there is no
    HTTP request at all (a REGISTRY action dispatch), so a minimal object
    exposing only ``.user`` stands in, since ``has_object_permission`` reads
    only ``request.user``.
    """
    if account is None:
        return False
    request = SimpleNamespace(user=account)
    return CanMarkBeat().has_object_permission(request, None, beat)  # type: ignore[arg-type]


@dataclass
class RunBeatAction(Action):
    """GM: instantiate a beat's authored session prep into the live scene (#3425).

    Kwarg: ``beat_id``. Gated by ``IsSceneGMPrerequisite`` (the actor must be
    running the scene at their location, or staff) plus
    ``MinimumGMLevelPrerequisite(JUNIOR)`` (this mints live ``CombatEncounter``/
    ``ChallengeInstance`` rows, the same tier as ``SetSituationAction``/
    ``PlaceChallengeAction``). A further check that the acting GM actually runs
    the beat's *story* (not just this scene) is re-verified in ``execute()`` via
    ``_actor_may_run_beat`` -- the prerequisite chain alone only proves general
    GM standing over this scene, not story-level authority over an arbitrary
    beat id supplied in the kwargs.

    Refuses TASK/REQUIREMENT kinds (nothing to stage) and refuses when the
    scene is already running a *different* beat; re-running the same beat is
    an idempotent no-op (the pointer write is skipped, and the response says
    so) rather than a second refused attempt, since a GM who presses the
    button twice should never spawn a second copy of the roster.

    Partial-failure rule: each opponent/staged-template line runs in its own
    savepoint and failures are logged and skipped rather than aborting the
    whole run -- the mission-grant pattern (log-and-continue, per-line
    outcomes reported in ``result.data``) rather than an all-or-nothing
    transaction, since a single bad line (e.g. a deleted creature template)
    should not cost the GM every other line they authored.
    """

    key: str = "run_beat"
    name: str = "Run Beat"
    icon: str = "play"
    category: str = "gm"
    target_type: TargetType = TargetType.SELF
    costs_turn: bool = False

    def get_prerequisites(self) -> list[Prerequisite]:
        return [IsSceneGMPrerequisite(), MinimumGMLevelPrerequisite(GMLevel.JUNIOR)]

    def _resolve_run_context(
        self, actor: ObjectDB, kwargs: dict[str, Any]
    ) -> tuple[Beat, Scene, AccountDB | None] | ActionResult:
        """Resolve + validate the beat/scene/account triple, or a failure result."""
        from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415

        beat_id = kwargs.get("beat_id")
        if beat_id is None:
            return ActionResult(success=False, message=_NO_BEAT)

        try:
            beat = Beat.objects.select_related("episode__chapter__story__primary_table").get(
                pk=beat_id
            )
        except (Beat.DoesNotExist, ValueError, TypeError):
            return ActionResult(success=False, message=_NO_SUCH_BEAT)

        if beat.kind not in _RUNNABLE_KINDS:
            return ActionResult(success=False, message=_NOT_RUNNABLE_KIND)

        account = resolve_account_or_none(actor)
        if not _actor_may_run_beat(account, beat):
            return ActionResult(success=False, message=_NO_BEAT_PERMISSION)

        scene = get_active_scene(actor.location)
        if scene is None:
            return ActionResult(success=False, message=_NO_ACTIVE_SCENE)

        if scene.running_beat_id is not None and scene.running_beat_id != beat.pk:
            return ActionResult(success=False, message=_ALREADY_RUNNING_OTHER)

        return beat, scene, account

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        resolved = self._resolve_run_context(actor, kwargs)
        if isinstance(resolved, ActionResult):
            return resolved
        beat, scene, account = resolved

        if scene.running_beat_id == beat.pk:
            return ActionResult(
                success=True,
                message=f"Scene is already running Beat #{beat.pk}.",
                data={"beat_id": beat.pk, "already_running": True},
            )

        scene.running_beat = beat
        scene.save(update_fields=["running_beat"])

        if beat.kind == BeatKind.ENCOUNTER:
            data = self._run_encounter_beat(beat, scene, account)
        else:
            data = self._run_situation_beat(actor, beat, scene)
        data["beat_id"] = beat.pk

        return ActionResult(
            success=True,
            message=f"Beat #{beat.pk} is now running in this scene.",
            data=data,
        )

    def _run_encounter_beat(
        self, beat: Beat, scene: Scene, account: AccountDB | None
    ) -> dict[str, Any]:
        """Create the CombatEncounter and spawn every authored opponent line."""
        from world.areas.positioning.exceptions import PositionError  # noqa: PLC0415
        from world.combat.models import CombatEncounter  # noqa: PLC0415
        from world.combat.services import (  # noqa: PLC0415
            finalize_new_encounter,
            spawn_from_creature_template,
            update_encounter_settings,
        )

        encounter = CombatEncounter.objects.create(scene=scene)
        finalize_new_encounter(encounter)
        encounter.story_beat = beat
        encounter.save(update_fields=["story_beat"])
        update_encounter_settings(encounter, risk_level=_RISK_MAP.get(beat.risk, "low"))

        room = encounter.room
        outcomes: list[dict[str, Any]] = []
        lines = beat.opponent_lines.select_related("creature_template").order_by("order")
        for line in lines:
            position = None
            note = ""
            if line.position_name and room is not None:
                try:
                    position = resolve_position_by_name(room, line.position_name)
                except CommandError:
                    note = f"position '{line.position_name}' not found; spawned without it"
            for _index in range(line.count):
                try:
                    with transaction.atomic():
                        opponent = spawn_from_creature_template(
                            encounter,
                            line.creature_template,
                            position=position,
                            acting_account=account,
                        )
                except (ValueError, PositionError) as exc:
                    # Per-line log-and-continue: a bad line (e.g. the encounter's
                    # scaling formula rejecting the template, or a cross-room
                    # position) never costs the GM every other authored line.
                    logger.warning(
                        "run_beat: failed to spawn opponent line %s (beat %s): %s",
                        line.pk,
                        beat.pk,
                        exc,
                    )
                    outcomes.append(
                        {
                            "line_id": line.pk,
                            "creature": line.creature_template.name,
                            "success": False,
                            "message": str(exc),
                        }
                    )
                    continue
                outcomes.append(
                    {
                        "line_id": line.pk,
                        "creature": line.creature_template.name,
                        "opponent_id": opponent.pk,
                        "success": True,
                        "message": note,
                    }
                )
        return {
            "encounter_id": encounter.pk,
            "risk_level": encounter.risk_level,
            "opponents": outcomes,
        }

    def _run_situation_beat(self, actor: ObjectDB, beat: Beat, scene: Scene) -> dict[str, Any]:
        """Instantiate every authored situation/challenge staged template."""
        from world.mechanics.challenge_resolution import instantiate_challenge  # noqa: PLC0415
        from world.mechanics.situation_services import (  # noqa: PLC0415
            create_challenge_target_object,
            instantiate_situation,
        )

        location = scene.location
        if location is None:
            return {"staged": [], "message": "Scene has no room; nothing was staged."}

        placed_by_sheet = actor.character_sheet
        outcomes: list[dict[str, Any]] = []
        lines = beat.staged_templates.select_related(
            "situation_template", "challenge_template"
        ).order_by("order")
        for line in lines:
            try:
                with transaction.atomic():
                    if line.situation_template_id is not None:
                        instantiate_situation(
                            line.situation_template,
                            location,
                            placed_by_sheet=placed_by_sheet,
                        )
                        label = line.situation_template.name
                    else:
                        target = create_challenge_target_object(line.challenge_template.name)
                        instantiate_challenge(
                            line.challenge_template,
                            location=location,
                            target_object=target,
                        )
                        label = line.challenge_template.name
            except (ValueError, ObjectDoesNotExist) as exc:
                # Per-line log-and-continue (see the opponent-line loop above) —
                # ObjectDoesNotExist covers instantiate_situation's "no
                # RoomProfile for traps" case.
                logger.warning(
                    "run_beat: failed to place staged template %s (beat %s): %s",
                    line.pk,
                    beat.pk,
                    exc,
                )
                outcomes.append({"template_id": line.pk, "success": False, "message": str(exc)})
                continue
            outcomes.append({"template_id": line.pk, "label": label, "success": True})
        return {"staged": outcomes}


@dataclass
class GMListRunnableBeatsAction(Action):
    """GM: list ENCOUNTER/SITUATION beats runnable at the acting GM's current tables (#3425).

    Read-only survey (the ``list_room_traps`` result-data pattern: rows in
    ``result.data["beats"]``, a human-readable joined line per row in
    ``result.message``). Scoped to episodes currently active (per
    ``get_active_progress_for_story``) on stories the acting GM runs: staff see
    every table-assigned story; a non-staff GM sees only stories where they are
    the Lead GM (``primary_table.gm``) -- the same Lead-GM chain
    ``CanMarkBeat``/``RunBeatAction`` gate on, so nothing appears here that
    ``run_beat`` would then refuse. ``internal_description`` is never included
    in the row payload (GM-only authoring text stays off this list surface).
    """

    key: str = "gm_list_runnable_beats"
    name: str = "List Runnable Beats"
    icon: str = "list"
    category: str = "gm"
    target_type: TargetType = TargetType.SELF
    costs_turn: bool = False

    def get_prerequisites(self) -> list[Prerequisite]:
        return [MinimumGMLevelPrerequisite(GMLevel.JUNIOR)]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.stories.models import Story  # noqa: PLC0415
        from world.stories.services.progress import get_active_progress_for_story  # noqa: PLC0415

        account = resolve_account_or_none(actor)
        empty = ActionResult(success=True, message="No runnable beats.", data={"beats": []})
        if account is None:
            return empty

        stories = Story.objects.filter(primary_table__isnull=False).select_related("primary_table")
        if not account.is_staff:
            stories = [s for s in stories if _actor_is_lead_gm(account, s)]

        rows: list[dict[str, Any]] = []
        for story in stories:
            progress = get_active_progress_for_story(story)
            episode = progress.current_episode if progress is not None else None
            if episode is None:
                continue
            beats = episode.beats.filter(kind__in=_RUNNABLE_KINDS)
            rows.extend(
                {
                    "id": beat.pk,
                    "story_title": story.title,
                    "episode_title": episode.title,
                    "kind": beat.kind,
                    "risk": beat.risk,
                    "opponent_line_count": beat.opponent_lines.count(),
                    "staged_template_count": beat.staged_templates.count(),
                }
                for beat in beats
            )

        if not rows:
            return empty

        lines = [
            f"[{r['id']}] {r['story_title']} / {r['episode_title']} ({r['kind']}, risk={r['risk']})"
            for r in rows
        ]
        return ActionResult(success=True, message="\n".join(lines), data={"beats": rows})
