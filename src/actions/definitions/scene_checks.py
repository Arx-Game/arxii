"""Scene check invocation: player self-checks, GM calls, and the proposal pipeline (#3295).

Governing invariant (Tehom, 2026-08-21 -- restates #2118's RATIFIED firewall): every
check anyone rolls in a scene is an authored ``CheckType`` from the catalog, at a
``DifficultyChoice`` band -- never a freeform stat/skill/difficulty invention. None of
the actions here select, compose, or fire a ``ConsequenceOutcome``/consequence pool;
each only resolves a catalog reference + band (via ``world.checks.catalog_invocation``,
the same shared core the SENIOR ad-hoc ``InvokeCatalogCheckAction`` uses) and fires
``perform_check`` as-is. When the catalog lacks a fitting check, ``ProposeCheckAction``
routes a structured proposal to the staff inbox -- it never creates a live ``CheckType``
row.

Five actions:
- ``SceneSelfCheckAction`` -- any player, SELF-target only, broadcasts to the room.
- ``CallForCheckAction`` -- JUNIOR+ GM, names target(s), creates a room-visible
  ``CheckCall`` prompt.
- ``AnswerCheckCallAction`` / ``DeclineCheckCallAction`` -- a named target's one-tap
  answer/decline. Answering dispatches the SAME self-check core, bound to the call's
  own catalog ref + band (the target never picks their own).
- ``ProposeCheckAction`` -- anyone, routes a structured proposal to the staff inbox.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.utils import timezone

from actions.base import Action
from actions.prerequisites import (
    HasCharacterSheetPrerequisite,
    MinimumGMLevelPrerequisite,
    Prerequisite,
)
from actions.types import ActionContext, ActionResult, TargetType
from world.checks.constants import CheckCallTargetStatus
from world.gm.constants import GMLevel
from world.scenes.action_constants import DIFFICULTY_VALUES, DifficultyChoice
from world.scenes.constants import InteractionMode

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.checks.models import CheckType

_SELF_CHECK_HINT = "No such check -- try `check find <term>`."
_CALL_CHECK_HINT = "No such check -- try `check find <term>`."
MSG_NO_SHEET = "You have no character sheet."
MSG_NO_PENDING_CALL = "No pending check call found for you."


def _resolve_target_sheets(raw_targets: Any) -> list[CharacterSheet]:
    """Resolve a list of int pks / ObjectDBs (REST + telnet shapes) to CharacterSheets.

    Mirrors ``_resolve_gm_target`` (``gm_adjudication.py``)'s dual-shape handling but
    for a list: telnet always passes resolved ``ObjectDB``s; the REST dispatch path
    passes raw ints (#2163/#3070 note -- ``objectdb_target_kwargs`` only auto-resolves
    a single websocket ``_id``-suffixed kwarg, never a list). Deduplicates by sheet pk
    and silently drops anything that doesn't resolve to a sheeted character.
    """
    from evennia.objects.models import ObjectDB  # noqa: PLC0415

    if raw_targets is None:
        return []
    if not isinstance(raw_targets, (list, tuple)):
        raw_targets = [raw_targets]

    sheets: list[CharacterSheet] = []
    seen_pks: set[int] = set()
    for raw in raw_targets:
        obj = raw if isinstance(raw, ObjectDB) else ObjectDB.objects.filter(pk=raw).first()
        if obj is None:
            continue
        sheet = obj.character_sheet
        if sheet is None or sheet.pk in seen_pks:
            continue
        seen_pks.add(sheet.pk)
        sheets.append(sheet)
    return sheets


def _perform_and_broadcast_self_check(
    actor: ObjectDB,
    actor_sheet: CharacterSheet,
    check_type: CheckType,
    band: str,
) -> ActionResult:
    """Fire ``perform_check`` and broadcast a number-free narration to the room.

    Shared by ``SceneSelfCheckAction`` and ``AnswerCheckCallAction`` -- the one place
    a catalog check actually rolls and reaches the scene feed. Attributes the
    broadcast to the roller's own currently-presenting persona (never
    ``actor.key``/the raw character name -- OUTCOME-mode interactions render with no
    payload-persona name at all, so the label MUST be embedded in the content, and it
    must be the presenting face to honor the #981 alt-leak rule).
    """
    from world.checks.services import perform_check  # noqa: PLC0415
    from world.scenes.interaction_services import (  # noqa: PLC0415
        record_interaction,
        render_challenge_outcome_narration,
    )
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    persona = active_persona_for_sheet(actor_sheet)
    result = perform_check(actor, check_type, target_difficulty=DIFFICULTY_VALUES[band])
    band_label = DifficultyChoice(band).label
    narration = render_challenge_outcome_narration(
        actor_label=persona.name,
        challenge_name=check_type.name,
        approach_name=band_label,
        outcome_label=result.outcome_name,
        success_level=result.success_level,
    )
    record_interaction(
        character=actor,
        content=narration,
        mode=InteractionMode.OUTCOME,
        persona=persona,
    )
    return ActionResult(success=True, message=narration)


@dataclass
class SceneSelfCheckAction(Action):
    """Any player rolls a catalog check on themselves, broadcast to the room (#3295).

    SELF-target only -- there is no ``target`` kwarg. Inputs are
    ``check_type_ref`` (pk-or-name, resolved via the shared catalog core) and a
    ``difficulty`` ``DifficultyChoice`` band -- the roller's own pick, echoed
    into the broadcast (theater, per Decision 2 -- no integers anywhere). The
    picker queryset includes the actor's own synthesized magic ``CheckType``
    (``owner_sheet`` set to their own sheet) but excludes every other
    character's, per ``catalog_queryset``'s existing scope.
    """

    key: str = "scene_self_check"
    name: str = "Roll a Check"
    icon: str = "dice"
    category: str = "checks"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [HasCharacterSheetPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.checks.catalog_invocation import (  # noqa: PLC0415
            resolve_band,
            resolve_check_type_ref,
        )

        actor_sheet = actor.character_sheet
        if actor_sheet is None:
            return ActionResult(success=False, message=MSG_NO_SHEET)

        resolved = resolve_check_type_ref(
            kwargs.get("check_type_ref"),
            owner_sheet=actor_sheet,
            not_found_hint=_SELF_CHECK_HINT,
        )
        if isinstance(resolved, ActionResult):
            return resolved
        check_type = resolved

        band_result = resolve_band(kwargs.get("difficulty"))
        if isinstance(band_result, ActionResult):
            return band_result
        band = band_result

        return _perform_and_broadcast_self_check(actor, actor_sheet, check_type, band)


@dataclass
class CallForCheckAction(Action):
    """A JUNIOR+ GM calls for a catalog check from named target(s) (#3295).

    Creates a room-visible ``CheckCall`` prompt (one ``CheckCallTarget`` row per
    resolved target) and broadcasts the call itself to the scene. Never rolls
    anything and never selects a consequence pool -- answering is each target's
    own separate action (``AnswerCheckCallAction``); declining is simply not
    answering (no mechanical force). ``check_type_ref`` resolves against the
    staff-authored catalog only (no ``owner_sheet``) -- a GM cannot call for a
    target's private synthesized magic check.
    """

    key: str = "call_for_check"
    name: str = "Call For a Check"
    icon: str = "megaphone"
    category: str = "gm"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [MinimumGMLevelPrerequisite(GMLevel.JUNIOR)]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.checks.catalog_invocation import (  # noqa: PLC0415
            resolve_band,
            resolve_check_type_ref,
        )
        from world.checks.models import CheckCall, CheckCallTarget  # noqa: PLC0415
        from world.scenes.interaction_services import (  # noqa: PLC0415
            get_active_scene,
            record_interaction,
        )
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        actor_sheet = actor.character_sheet
        if actor_sheet is None:
            return ActionResult(success=False, message=MSG_NO_SHEET)

        resolved = resolve_check_type_ref(
            kwargs.get("check_type_ref"), not_found_hint=_CALL_CHECK_HINT
        )
        if isinstance(resolved, ActionResult):
            return resolved
        check_type = resolved

        band_result = resolve_band(kwargs.get("difficulty"))
        if isinstance(band_result, ActionResult):
            return band_result
        band = band_result

        target_sheets = _resolve_target_sheets(kwargs.get("targets"))
        if not target_sheets:
            return ActionResult(
                success=False, message="Name at least one target to call the check on."
            )

        scene = get_active_scene(actor.location)
        if scene is None:
            return ActionResult(
                success=False,
                message="You must be running an active scene to call for a check.",
            )

        caller_persona = active_persona_for_sheet(actor_sheet)
        band_label = DifficultyChoice(band).label

        with transaction.atomic():
            call = CheckCall.objects.create(
                scene=scene,
                caller_persona=caller_persona,
                check_type=check_type,
                band=band,
            )
            CheckCallTarget.objects.bulk_create(
                CheckCallTarget(call=call, target_sheet=sheet) for sheet in target_sheets
            )

        target_names = ", ".join(active_persona_for_sheet(sheet).name for sheet in target_sheets)
        narration = (
            f"{caller_persona.name} calls for a check: {check_type.name} ({band_label}) "
            f"from {target_names}."
        )
        record_interaction(
            character=actor,
            content=narration,
            mode=InteractionMode.OUTCOME,
            persona=caller_persona,
        )
        return ActionResult(success=True, message=narration, data={"call_id": call.pk})


@dataclass
class AnswerCheckCallAction(Action):
    """A named target answers a ``CheckCall`` with the one-tap bound roll (#3295).

    The target never picks their own check/band -- both come from the call.
    Marks the ``CheckCallTarget`` row ANSWERED exactly once (a second answer
    attempt finds no PENDING row and refuses).
    """

    key: str = "answer_check_call"
    name: str = "Answer Check Call"
    icon: str = "dice"
    category: str = "checks"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [HasCharacterSheetPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.checks.models import CheckCallTarget  # noqa: PLC0415

        actor_sheet = actor.character_sheet
        if actor_sheet is None:
            return ActionResult(success=False, message=MSG_NO_SHEET)

        target_row = (
            CheckCallTarget.objects.filter(
                call_id=kwargs.get("call_id"),
                target_sheet=actor_sheet,
                status=CheckCallTargetStatus.PENDING,
            )
            .select_related("call__check_type")
            .first()
        )
        if target_row is None:
            return ActionResult(success=False, message=MSG_NO_PENDING_CALL)

        call = target_row.call
        result = _perform_and_broadcast_self_check(actor, actor_sheet, call.check_type, call.band)
        target_row.status = CheckCallTargetStatus.ANSWERED
        target_row.resolved_at = timezone.now()
        target_row.save(update_fields=["status", "resolved_at"])
        return result


@dataclass
class DeclineCheckCallAction(Action):
    """A named target declines a ``CheckCall`` -- not rolling, no mechanical force (#3295).

    Quiet by design: no room broadcast. The call stays visible to everyone else;
    this target simply stops being prompted.
    """

    key: str = "decline_check_call"
    name: str = "Decline Check Call"
    icon: str = "x"
    category: str = "checks"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [HasCharacterSheetPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.checks.models import CheckCallTarget  # noqa: PLC0415

        actor_sheet = actor.character_sheet
        if actor_sheet is None:
            return ActionResult(success=False, message=MSG_NO_SHEET)

        target_row = CheckCallTarget.objects.filter(
            call_id=kwargs.get("call_id"),
            target_sheet=actor_sheet,
            status=CheckCallTargetStatus.PENDING,
        ).first()
        if target_row is None:
            return ActionResult(success=False, message=MSG_NO_PENDING_CALL)

        target_row.status = CheckCallTargetStatus.DECLINED
        target_row.resolved_at = timezone.now()
        target_row.save(update_fields=["status", "resolved_at"])
        return ActionResult(success=True, message="You decline to roll.")


@dataclass
class ProposeCheckAction(Action):
    """Propose a new ``CheckType`` to staff -- never creates a live catalog row (#3295).

    The catalog-only ruling's escape valve (Tehom, 2026-08-21): when the
    catalog lacks a fitting check, propose one instead of inventing it on the
    spot. Structured columns only (name/intent/suggested traits/situation) --
    no JSON, no freeform stat+skill+difficulty. Routes to the staff inbox via
    ``world.player_submissions.services.submit_check_proposal``; adoption is a
    separate, manual staff act.
    """

    key: str = "propose_check_type"
    name: str = "Propose a Check"
    icon: str = "lightbulb"
    category: str = "checks"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [HasCharacterSheetPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from typeclasses.characters import Character  # noqa: PLC0415
        from world.player_submissions.services import submit_check_proposal  # noqa: PLC0415
        from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        actor_sheet = actor.character_sheet
        if actor_sheet is None:
            return ActionResult(success=False, message=MSG_NO_SHEET)

        proposed_name = str(kwargs.get("proposed_name") or "").strip()
        intent = str(kwargs.get("intent") or "").strip()
        situation_text = str(kwargs.get("situation_text") or "").strip()
        suggested_traits_text = str(kwargs.get("suggested_traits_text") or "").strip()

        if not proposed_name or not intent or not situation_text:
            return ActionResult(
                success=False,
                message="A proposal needs a name, its intent, and the situation it serves.",
            )

        account = actor.active_account if isinstance(actor, Character) else None
        if account is None:
            return ActionResult(success=False, message="No controlling account found.")

        persona = active_persona_for_sheet(actor_sheet)
        scene = get_active_scene(actor.location)

        submit_check_proposal(
            account,
            persona,
            proposed_name=proposed_name,
            intent=intent,
            situation_text=situation_text,
            suggested_traits_text=suggested_traits_text,
            scene=scene,
        )
        return ActionResult(success=True, message=f"Proposal for {proposed_name!r} sent to staff.")
