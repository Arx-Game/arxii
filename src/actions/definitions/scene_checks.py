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
    from world.checks.models import CheckCall, CheckType
    from world.worship.types import InvocationRequest

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


def _invocation_from_kwargs(
    actor_sheet: CharacterSheet, kwargs: dict[str, Any]
) -> InvocationRequest | ActionResult | None:
    """A Call on favor choice from the action's kwargs (#4333), checked.

    ``invoke_being_id`` (a ``WorshippedBeing`` pk) and an optional
    ``invoke_line``. Returns None when no being was chosen, or a failed
    ``ActionResult`` carrying the player-facing reason it was refused.
    """
    from world.worship.exceptions import FavorInvocationRefused  # noqa: PLC0415
    from world.worship.invocation_services import (  # noqa: PLC0415
        MSG_NO_SUCH_BEING,
        resolve_invocation_choice,
    )
    from world.worship.types import InvocationChoice  # noqa: PLC0415

    raw = kwargs.get("invoke_being_id")
    if raw in (None, ""):
        return None
    try:
        being_id = int(raw)
    except (TypeError, ValueError):
        return ActionResult(success=False, message=MSG_NO_SUCH_BEING)
    choice = InvocationChoice(being_id=being_id, player_line=str(kwargs.get("invoke_line") or ""))
    try:
        return resolve_invocation_choice(actor_sheet, choice)
    except FavorInvocationRefused as exc:
        return ActionResult(success=False, message=exc.user_message)


def _echo_to_telnet_bystanders(
    actor: ObjectDB, text: str, *, skip_ids: frozenset[int] = frozenset()
) -> None:
    """Send a room line to the non-web sessions of everyone else in the room.

    ``record_interaction`` pushes to the web only; the roller already gets the
    line as their result message, so they are skipped here, as is anyone in
    ``skip_ids`` (a check call's targets, who are told directly).
    """
    from world.scenes.interaction_services import non_web_sessions  # noqa: PLC0415

    location = actor.location
    if location is None:
        return
    for obj in location.contents:
        if obj.pk == actor.pk or obj.pk in skip_ids:
            continue
        sessions = non_web_sessions(obj)
        if sessions:
            obj.msg(text, session=sessions)


def _tell_check_targets(
    call: CheckCall, target_sheets: list[CharacterSheet], narration: str
) -> None:
    """Tell each called character the call and the two replies to type.

    ``record_interaction`` reaches the web only, and the narration carries no
    call id, so until #3657's journey asked a telnet target was never prompted
    and could not have answered (the same gap the org and event invites had).
    """
    for sheet in target_sheets:
        sheet.character.msg(
            f"{narration} check answer {call.pk} to roll, check decline {call.pk} to refuse."
        )


def _perform_and_broadcast_self_check(
    actor: ObjectDB,
    actor_sheet: CharacterSheet,
    check_type: CheckType,
    band: str,
    invocation: InvocationRequest | None = None,
) -> ActionResult:
    """Fire ``perform_check`` and broadcast a number-free narration to the room.

    Shared by ``SceneSelfCheckAction`` and ``AnswerCheckCallAction`` -- the one place
    a catalog check actually rolls and reaches the scene feed. Attributes the
    broadcast to the roller's own currently-presenting persona (never
    ``actor.key``/the raw character name -- OUTCOME-mode interactions render with no
    payload-persona name at all, so the label MUST be embedded in the content, and it
    must be the presenting face to honor the #981 alt-leak rule).

    The roller's own message ends with their standing (#4601): "Your standing: Expert
    (rank 3), 67% toward Master (rank 4) against Master (rank 4)." The broadcast does not.

    ``invocation`` (#4333): a Call on favor rolls first; its lines reach the room
    and its bonus is added to this check. The roller's result message carries
    their own line (for a secret faith the room line omits it) and the bonus.
    """
    from world.checks.services import perform_check  # noqa: PLC0415
    from world.scenes.interaction_services import (  # noqa: PLC0415
        get_active_scene,
        record_interaction,
        render_challenge_outcome_narration,
    )
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    persona = active_persona_for_sheet(actor_sheet)
    favor_lines: list[str] = []
    favor_bonus = 0
    if invocation is not None:
        from world.scenes.favor_invocation import (  # noqa: PLC0415
            broadcast_invocation,
            invocation_private_lines,
        )
        from world.worship.exceptions import FavorInvocationRefused  # noqa: PLC0415
        from world.worship.invocation_services import invoke_favor  # noqa: PLC0415

        scene = get_active_scene(actor.location)
        try:
            outcome = invoke_favor(
                actor_sheet,
                invocation.being,
                actor_name=persona.name,
                player_line=invocation.player_line,
                scene=scene,
            )
        except FavorInvocationRefused as exc:
            return ActionResult(success=False, message=exc.user_message)
        broadcast_invocation(outcome, persona=persona, scene=scene, location=actor.location)
        favor_bonus = outcome.bonus
        favor_lines = invocation_private_lines(outcome)
    result = perform_check(
        actor,
        check_type,
        target_difficulty=DIFFICULTY_VALUES[band],
        extra_modifiers=favor_bonus,
    )
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
    # On commit, after the invocation's own lines (also delivered on commit).
    transaction.on_commit(lambda: _echo_to_telnet_bystanders(actor, narration))
    # The roller alone reads where they stood: ranks with their numbers and how far
    # through the band each side sat (#4601). The room's narration stays number-free.
    standing_line = f"Your standing: {result.standing_text}." if result.standing_text else ""
    lines = [*favor_lines, narration, standing_line]
    return ActionResult(success=True, message="\n".join(line for line in lines if line))


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

        invocation = _invocation_from_kwargs(actor_sheet, kwargs)
        if isinstance(invocation, ActionResult):
            return invocation
        return _perform_and_broadcast_self_check(actor, actor_sheet, check_type, band, invocation)


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
        _tell_check_targets(call, target_sheets, narration)
        target_ids = frozenset(sheet.character.pk for sheet in target_sheets)
        transaction.on_commit(
            lambda: _echo_to_telnet_bystanders(actor, narration, skip_ids=target_ids)
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

        invocation = _invocation_from_kwargs(actor_sheet, kwargs)
        if isinstance(invocation, ActionResult):
            return invocation
        call = target_row.call
        result = _perform_and_broadcast_self_check(
            actor, actor_sheet, call.check_type, call.band, invocation
        )
        if not result.success:
            return result
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
