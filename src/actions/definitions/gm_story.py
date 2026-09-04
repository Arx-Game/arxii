"""GM session-prep run actions (#3425, scenario runs #3565).

A GM authors what a beat stages ahead of a session -- opponent lines
(``BeatOpponentLine``) or a staged battle (``BeatStagedBattle``, #3569) for
an ENCOUNTER beat, situation/challenge templates (``BeatStagedTemplate``) for
a SITUATION beat, or a mission scenario graph (``Beat.required_mission``) for
a TASK beat (and optionally alongside a SITUATION beat's staged templates)
-- and, at the table, presses "Run this beat" to instantiate all of it into
the live scene at once: ``RunBeatAction``. An ENCOUNTER beat with a
``BeatStagedBattle`` row stages a ``Battle`` from its blueprint instead of a
``CombatEncounter`` (``_run_battle_beat`` vs ``_run_encounter_beat``) -- a
beat carries either opponent lines or a staged battle, never both
(``BeatStagedBattle.clean``). A beat with ``required_mission`` set starts
(or rejoins) that scenario for the whole scene's party via
``world.missions.services.run.start_scenario_for_scene`` -- the beat's
authored options play out as story choices on the mission graph rather than
a bespoke option engine (#3565). ``GMListRunnableBeatsAction`` is the read
side that feeds the web "Run Beat" tab (and telnet, if a future command
wants it) a scoped list of runnable beats -- ENCOUNTER/SITUATION beats, plus
any TASK beat that carries a scenario (``has_scenario``) -- on episodes the
acting GM currently runs; each row's ``staged_battle_name`` names the
blueprint an ENCOUNTER beat will stage from, or None.

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
from django.db.models import Q

from actions.base import Action
from actions.definitions.gm_stories import _actor_is_lead_gm
from actions.prerequisites import IsSceneGMPrerequisite, MinimumGMLevelPrerequisite, Prerequisite
from actions.types import ActionContext, ActionResult, TargetType
from commands.utils.gm_resolution import resolve_account_or_none
from world.gm.constants import GMLevel
from world.societies.constants import RenownRisk
from world.stories.constants import BeatKind
from world.stories.models import Beat, BeatStagedBattle
from world.stories.permissions import CanMarkBeat

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB

    from world.scenes.models import Scene

logger = logging.getLogger(__name__)

_NOT_RUNNABLE_KIND = (
    "Only ENCOUNTER and SITUATION beats, or a TASK beat with a scenario, can be run into a scene."
)
_NO_BEAT = "A beat is required."
_NO_SUCH_BEAT = "No beat with that ID exists."
_NO_BEAT_PERMISSION = "You do not have authority over this beat's story."
_NO_ACTIVE_SCENE = "There is no active scene here."
_ALREADY_RUNNING_OTHER = "This scene is already running a different beat."
_ALREADY_RUNNING_ELSEWHERE = "Another active scene is already running this beat."
_NO_CLOCK = "This scene has no clock to advance."
_BAD_BY = "by must be a whole number of at least 1."

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

_RUNNABLE_KINDS = (BeatKind.ENCOUNTER, BeatKind.SITUATION, BeatKind.TASK)


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

    Refuses REQUIREMENT kinds and a TASK beat with no scenario (nothing to
    run), and refuses when the scene is already running a *different* beat;
    re-running the same beat is an idempotent no-op (the pointer write is
    skipped, and the response says so) rather than a second refused attempt,
    since a GM who presses the button twice should never spawn a second copy
    of the roster.

    A beat carrying a scenario (``required_mission`` set -- always true for
    a runnable TASK beat, optionally true for a SITUATION beat alongside its
    staged templates) also starts that scenario for the scene's whole party
    via ``start_scenario_for_scene`` (#3565), reusing (never duplicating) an
    already-ACTIVE run for the same beat -- the same run ``gm_assign_mission``
    may have started for one character earlier. The new run/rejoin's id
    surfaces in ``result.data["scenario_instance_id"]``.

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

        if beat.kind == BeatKind.TASK and beat.required_mission_id is None:
            return ActionResult(success=False, message=_NOT_RUNNABLE_KIND)

        account = resolve_account_or_none(actor)
        if not _actor_may_run_beat(account, beat):
            return ActionResult(success=False, message=_NO_BEAT_PERMISSION)

        scene = get_active_scene(actor.location)
        if scene is None:
            return ActionResult(success=False, message=_NO_ACTIVE_SCENE)

        if scene.running_beat_id is not None and scene.running_beat_id != beat.pk:
            return ActionResult(success=False, message=_ALREADY_RUNNING_OTHER)

        if scene.running_beat_id != beat.pk:
            from world.scenes.models import Scene as SceneModel  # noqa: PLC0415

            # #3567: one running scene per beat, so a clock never couples two
            # tables. A battle this beat staged runs the same beat on its own
            # private scene by design (``_run_battle_beat``); exclude it.
            elsewhere = (
                SceneModel.objects.filter(running_beat=beat, is_active=True)
                .exclude(pk=scene.pk)
                .exclude(battle__story_beat=beat)
            )
            if elsewhere.exists():
                return ActionResult(success=False, message=_ALREADY_RUNNING_ELSEWHERE)

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

        from world.scenes.clock_services import start_scene_clock  # noqa: PLC0415

        clock = start_scene_clock(scene, beat)

        if beat.kind == BeatKind.ENCOUNTER:
            staged = (
                BeatStagedBattle.objects.filter(beat=beat)
                .select_related("blueprint", "region")
                .first()
            )
            if staged is not None:
                data = self._run_battle_beat(beat, staged, scene, account)
            else:
                data = self._run_encounter_beat(beat, scene, account)
        else:
            if beat.kind == BeatKind.SITUATION:
                data = self._run_situation_beat(actor, beat, scene)
            else:
                data = {}
            if beat.required_mission_id is not None:
                from world.missions.services.run import start_scenario_for_scene  # noqa: PLC0415

                instance = start_scenario_for_scene(beat, scene)
                data["scenario_instance_id"] = instance.pk
        data["beat_id"] = beat.pk
        if clock is not None:
            data["clock"] = {"size": clock.size, "filled": clock.filled}

        return ActionResult(
            success=True,
            message=f"Beat #{beat.pk} is now running in this scene.",
            data=data,
        )

    def _run_encounter_beat(
        self, beat: Beat, scene: Scene, account: AccountDB | None
    ) -> dict[str, Any]:
        """Create the CombatEncounter and spawn every authored opponent line."""
        from world.combat.encounter_prep import spawn_opponent_lines  # noqa: PLC0415
        from world.combat.models import CombatEncounter  # noqa: PLC0415
        from world.combat.services import (  # noqa: PLC0415
            finalize_new_encounter,
            update_encounter_settings,
        )

        encounter = CombatEncounter.objects.create(scene=scene)
        finalize_new_encounter(encounter)
        encounter.story_beat = beat
        encounter.save(update_fields=["story_beat"])
        update_encounter_settings(encounter, risk_level=_RISK_MAP.get(beat.risk, "low"))

        lines = beat.opponent_lines.select_related("creature_template").order_by("order")
        outcomes = spawn_opponent_lines(encounter, lines, acting_account=account)
        return {
            "encounter_id": encounter.pk,
            "risk_level": encounter.risk_level,
            "opponents": outcomes,
        }

    def _run_battle_beat(
        self,
        beat: Beat,
        staged: BeatStagedBattle,
        scene: Scene,
        account: AccountDB | None,
    ) -> dict[str, Any]:
        """Stage the beat's battle from its blueprint, link it, spawn, enlist (#3569).

        Idempotent: re-running a beat whose battle already exists and hasn't
        concluded returns that same battle (``already_staged=True``) instead of
        staging a second one. Otherwise stages a ``Battle`` from
        ``staged.blueprint`` at the beat's mapped risk, routes it to this beat
        (``Battle.story_beat``, so ``activate_stakes_for_battle`` and
        ``resolve_battle_beats`` scope to it), sets ``battle.scene.running_beat``
        so the battle's own scene (where the web navigates and where
        ``stakes-summary`` reads from) shows this beat's declared-risk badge --
        not just the GM's original scene, which ``execute()`` already stamps --
        links the battle's Scene to the beat's episode (``EpisodeScene``), grants
        the running GM ``is_gm`` on that Scene (mirroring ``CreateBattleAction``),
        spawns every authored
        unit line, and enlists every active non-GM participant of the running
        scene on ``staged.party_side_role``.
        """
        from world.battles.models import Battle  # noqa: PLC0415
        from world.battles.staging import stage_battle  # noqa: PLC0415
        from world.scenes.models import SceneParticipation  # noqa: PLC0415
        from world.stories.models import EpisodeScene  # noqa: PLC0415

        existing = Battle.objects.filter(story_beat=beat).order_by("-pk").first()
        if existing is not None and not existing.is_concluded:
            return {
                "battle_id": existing.pk,
                "battle_scene_id": existing.scene_id,
                "already_staged": True,
            }

        description = beat.internal_description.strip()
        if staged.name:
            name = staged.name
        elif description:
            name = description.splitlines()[0][:100]
        else:
            name = f"Beat #{beat.pk}"

        with transaction.atomic():
            battle = stage_battle(
                name=name,
                risk_level=_RISK_MAP.get(beat.risk, "low"),
                blueprint=staged.blueprint,
                campaign_story=beat.episode.chapter.story,
                region=staged.region,
                location=scene.location,
            )
            battle.story_beat = beat
            battle.save(update_fields=["story_beat"])
            battle.scene.running_beat = beat
            battle.scene.save(update_fields=["running_beat"])
            EpisodeScene.objects.get_or_create(
                episode=beat.episode,
                scene=battle.scene,
                defaults={"order": EpisodeScene.objects.filter(scene=battle.scene).count()},
            )
            if account is not None:
                SceneParticipation.objects.update_or_create(
                    scene=battle.scene,
                    account=account,
                    defaults={"is_gm": True},
                )

        sides = {side.role: side for side in battle.sides.all()}
        units = self._spawn_staged_battle_units(staged, battle, sides)
        enlisted = self._enlist_scene_party(scene, battle, sides[staged.party_side_role])

        return {
            "battle_id": battle.pk,
            "battle_scene_id": battle.scene_id,
            "risk_level": battle.risk_level,
            "units": units,
            "enlisted": enlisted,
            "already_staged": False,
        }

    def _spawn_staged_battle_units(
        self,
        staged: BeatStagedBattle,
        battle: Any,
        sides: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Spawn every authored unit line onto *battle*; log-and-continue per line."""
        from world.battles.staging import spawn_units_from_template  # noqa: PLC0415

        places = {place.name: place for place in battle.places.all()}
        units: list[dict[str, Any]] = []
        for line in staged.unit_lines.select_related("template").order_by("order", "pk"):
            place = places.get(line.place_name) if line.place_name else None
            if line.place_name and place is None:
                logger.warning(
                    "run_beat: staged unit line %s names unknown place %r; spawning unplaced",
                    line.pk,
                    line.place_name,
                )
            try:
                with transaction.atomic():
                    spawned = spawn_units_from_template(
                        line.template,
                        battle=battle,
                        side=sides[line.side_role],
                        place=place,
                        count=line.count,
                    )
            except (KeyError, ValueError, ObjectDoesNotExist) as exc:
                logger.exception("run_beat: staged unit line %s failed to spawn", line.pk)
                units.append({"line_id": line.pk, "success": False, "message": str(exc)})
                continue
            units.append({"line_id": line.pk, "success": True, "unit_ids": [u.pk for u in spawned]})
        return units

    def _enlist_scene_party(self, scene: Scene, battle: Any, party_side: Any) -> list[int]:
        """Enlist only the PRESENT sheets of active non-GM scene participants (#3569).

        ``RosterEntry.objects.for_account(account)`` alone returns every
        currently-tenured character of an account -- an account playing two
        characters at once (a PC plus a companion/alt elsewhere) would get
        the one NOT standing in this scene's room swept in too (fix round 1,
        follow-up to 29219b1b0). Narrowed to characters physically present at
        ``scene.location`` (``location.contents``) -- the same room-presence
        check ``actions.definitions.gm_stories._present_participant_sheets``
        already applies for stakes declaration, whose own docstring names
        this exact trap: "an account's off-scene alts must not skew...".
        ``scene.persona_handler.active_participant_personas()`` was
        considered directly, but it does not itself narrow to the present
        room (it walks every available character of every participating
        account, same as ``for_account``) or exclude participants who left
        the scene (``participations_cached`` carries every row, ``left_at``
        included) -- the pre-existing ``is_gm=False, left_at__isnull=True``
        participation filter stays the authority for GM/left exclusion; the
        room-presence check is layered on top of it, not instead of it.
        """
        from world.battles.services import enlist_participant  # noqa: PLC0415
        from world.roster.models import RosterEntry  # noqa: PLC0415

        location = scene.location
        present_ids = {obj.pk for obj in location.contents} if location is not None else set()
        already_enlisted = set(battle.participants.values_list("character_sheet_id", flat=True))

        enlisted: list[int] = []
        participations = scene.participations.filter(
            is_gm=False, left_at__isnull=True
        ).select_related("account")
        for participation in participations:
            for entry in RosterEntry.objects.for_account(participation.account):
                sheet = entry.character_sheet
                if sheet.character_id not in present_ids:
                    continue
                if sheet.pk in already_enlisted:
                    continue
                enlist_participant(battle=battle, character_sheet=sheet, side=party_side)
                already_enlisted.add(sheet.pk)
                enlisted.append(sheet.pk)
        return enlisted

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
    """GM: list beats runnable at the acting GM's current tables (#3425, #3565).

    Read-only survey (the ``list_room_traps`` result-data pattern: rows in
    ``result.data["beats"]``, a human-readable joined line per row in
    ``result.message``). A row is ENCOUNTER, SITUATION, or a TASK beat that
    carries a scenario (``required_mission`` set); each row's
    ``has_scenario`` flags whether ``run_beat`` will also start that beat's
    mission scenario for the scene (#3565). Scoped to episodes currently
    active (per ``get_active_progress_for_story``) on stories the acting GM
    runs: staff see every table-assigned story; a non-staff GM sees only
    stories where they are the Lead GM (``primary_table.gm``) -- the same
    Lead-GM chain ``CanMarkBeat``/``RunBeatAction`` gate on, so nothing
    appears here that ``run_beat`` would then refuse.
    ``internal_description`` is never included in the row payload (GM-only
    authoring text stays off this list surface).
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

        beats_by_story: list[tuple[Any, Any, list[Beat]]] = []
        all_beats: list[Beat] = []
        for story in stories:
            progress = get_active_progress_for_story(story)
            episode = progress.current_episode if progress is not None else None
            if episode is None:
                continue
            beats = list(
                episode.beats.filter(
                    Q(kind__in=(BeatKind.ENCOUNTER, BeatKind.SITUATION))
                    | Q(kind=BeatKind.TASK, required_mission__isnull=False)
                )
            )
            beats_by_story.append((story, episode, beats))
            all_beats.extend(beats)

        # One query for staged-battle names across every row (never per-row, #3569).
        staged_battle_names = {
            row.beat_id: row.blueprint.name
            for row in BeatStagedBattle.objects.filter(
                beat_id__in=[beat.pk for beat in all_beats]
            ).select_related("blueprint")
        }

        rows: list[dict[str, Any]] = []
        for story, episode, beats in beats_by_story:
            rows.extend(
                {
                    "id": beat.pk,
                    "story_title": story.title,
                    "episode_title": episode.title,
                    "kind": beat.kind,
                    "risk": beat.risk,
                    "opponent_line_count": beat.opponent_lines.count(),
                    "staged_template_count": beat.staged_templates.count(),
                    "has_scenario": beat.required_mission_id is not None,
                    "staged_battle_name": staged_battle_names.get(beat.pk),
                    "clock_size": beat.clock_size,
                }
                for beat in beats
            )

        if not rows:
            return empty

        lines = [
            f"[{r['id']}] {r['story_title']} / {r['episode_title']} ({r['kind']}, risk={r['risk']})"
            + (f" clock {r['clock_size']}" if r["clock_size"] > 0 else "")
            for r in rows
        ]
        return ActionResult(success=True, message="\n".join(lines), data={"beats": rows})


@dataclass
class AdvanceClockAction(Action):
    """GM: spend ticks on the running beat's scene clock (#3567).

    Kwarg ``by`` (default 1, whole number >= 1). Pacing, not outcome: the
    size and the EXPIRED consequence are authored on the beat; this only
    spends the ticks the fiction consumed. Filling completes the beat EXPIRED
    after this request commits (``clock_services.tick_scene_clock``).
    """

    key: str = "advance_clock"
    name: str = "Advance Clock"
    icon: str = "clock"
    category: str = "gm"
    target_type: TargetType = TargetType.SELF
    costs_turn: bool = False

    def get_prerequisites(self) -> list[Prerequisite]:
        return [IsSceneGMPrerequisite(), MinimumGMLevelPrerequisite(GMLevel.JUNIOR)]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.scenes.clock_services import tick_scene_clock  # noqa: PLC0415
        from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415

        by = kwargs.get("by", 1)
        if isinstance(by, bool) or not isinstance(by, int) or by < 1:
            return ActionResult(success=False, message=_BAD_BY)
        scene = get_active_scene(actor.location)
        if scene is None:
            return ActionResult(success=False, message=_NO_ACTIVE_SCENE)
        clock = tick_scene_clock(scene, by=by)
        if clock is None:
            return ActionResult(success=False, message=_NO_CLOCK)
        filled_now = clock.closed_at is not None
        message = (
            f"The clock fills: {clock.filled}/{clock.size}. Time is up."
            if filled_now
            else f"The clock advances: {clock.filled}/{clock.size}."
        )
        return ActionResult(
            success=True,
            message=message,
            data={"size": clock.size, "filled": clock.filled, "filled_now": filled_now},
        )
