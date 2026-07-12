"""IdentifyAction — see through a mask or disguise to who's really underneath (#1107 slice 5).

**Not** an ActionTemplate-driven ``_SocialTemplateAction`` like Deceive/Persuade/Seduce
(``actions/definitions/social.py``): ``attempt_identification``
(``world.forms.services.identification``) already owns its own bespoke check pipeline — a
custom difficulty table (familiarity/fame eases, a named-guess ease), a direct
``perform_check`` roll against that computed difficulty, and its own outcome branching
(SUCCESS/FAILURE/BOTCH_FAKE_ID/ALREADY_KNOWN/AUTO_FAIL) with a ``PersonaDiscovery`` write on
success. None of that fits the ActionTemplate/ConsequencePool pipeline
``start_action_resolution`` drives (fixed ``target_difficulty=0``, gate/consequence-pool
resolution, NPC disposition delta) — and identification's outcome message must stay
roller-only (the spec's oracle rule: FAILURE and AUTO_FAIL are player-indistinguishable, and
a BOTCH must never name a real PC), unlike social template actions whose consequences are
narrated into the scene. A plain registry action thinly wrapping the service directly is the
repo's other established idiom for this shape (``battles.py``, ``sanctum.py``,
``relationships.py`` — ``Action`` subclasses calling a service function with no
ActionTemplate involved).

Not auto-surfaced to the web dynamic action panel like the ActionTemplate-backed social
actions are (``_scene_actions`` in ``actions/player_interface.py`` only picks up
``ActionTemplate`` rows) — and deliberately NOT given a bespoke web-panel adapter either,
unlike the #2005/#2010 battle-staging precedent (``_positioning_actions``/
``_battle_staging_actions``). Every consumer of ``get_player_actions`` (``ActionPanel.tsx``,
``PersonaContextMenu.tsx``) dispatches its listed entries through the CONSENT pipeline
(``createActionRequest``), which identify — a no-consent private perception roll, ADR-0024 —
must never enter (#1107 Task 3 review, Critical finding: it would both hand the masked
target a veto it shouldn't have and crash on accept, no ``ActionTemplate``/
``CUSTOM_ACTION_RESOLVERS`` entry to resolve against). Its only web path is a dedicated
"Identify" item in ``PersonaContextMenu`` that dispatches REGISTRY REST directly
(``useDispatchPlayerAction`` -> ``_dispatch_registry`` -> ``.run()``), mirroring that menu's
pre-existing ``challenge`` dispatch; telnet reaches it via ``CmdIdentify``
(``commands/identification.py``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.constants import ActionCategory, TargetKind
from actions.prerequisites import Prerequisite, resolve_actor_sheet
from actions.types import ActionResult, TargetFilters, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext
    from world.scenes.models import Persona

_NO_TARGET_MESSAGE = "Identify whom?"
_NOT_PRESENT_MESSAGE = "They aren't here."
_NOTHING_TO_SEE_MESSAGE = "Their face is their own — there is no mask to see through."


def _resolve_persona_pk_to_character(persona_id: Any) -> ObjectDB | None:
    """Resolve a ``Persona`` pk to its owning character ``ObjectDB``, or ``None``."""
    from world.scenes.models import Persona  # noqa: PLC0415

    persona = Persona.objects.filter(pk=persona_id).select_related("character_sheet").first()
    if persona is None:
        return None
    return persona.character_sheet.character


def _resolve_identify_target(kwargs: dict[str, Any]) -> ObjectDB | None:
    """Resolve the identify target from any dispatch shape (#1107 Task 3, the #2163 gotcha;
    hardened in the Task 3 review's Minor finding 1).

    Three shapes are accepted, all keyed off ``target``/``target_persona_id``:

    - Telnet passes an already-resolved ``target`` ``ObjectDB`` directly.
    - The ``PersonaContextMenu`` "Identify" item (web) sends a raw ``target`` kwarg holding a
      ``Persona`` pk (an ``int``) — mirroring ``ChallengeAction``'s
      ``_resolve_challenge_target`` (``actions/definitions/duels.py``), the established
      precedent for a context-menu-dispatched persona-pk ``target`` kwarg.
    - The generic web REGISTRY dispatch convention instead sends ``target_persona_id`` (a
      ``Persona`` pk) — kept for back-compat with the #2163 REST-dispatch gotcha this
      resolver was originally written to cover.

    REST dispatch (``dispatch_player_action`` -> ``_dispatch_registry``) does no ``ObjectDB``
    resolution of its own; ``objectdb_target_kwargs`` only helps the *websocket* inputfunc, and
    only for wire keys it's told about. Resolve defensively here so every dispatch shape works,
    shared by the prerequisite gate and ``execute()``.
    """
    from evennia.objects.models import ObjectDB  # noqa: PLC0415

    target = kwargs.get("target")
    if isinstance(target, ObjectDB):
        return target
    if target is not None:
        return _resolve_persona_pk_to_character(target)

    persona_id = kwargs.get("target_persona_id")
    if persona_id is None:
        return None
    return _resolve_persona_pk_to_character(persona_id)


def _presented_fake_persona(target_obj: ObjectDB) -> Persona | None:
    """The target's active persona iff it is a fake-name mask, else ``None``."""
    from world.scenes.models import Persona  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    target_sheet = resolve_actor_sheet(target_obj)
    if target_sheet is None:
        return None
    try:
        presented = active_persona_for_sheet(target_sheet)
    except Persona.DoesNotExist:
        return None
    return presented if presented.is_fake_name else None


def _is_viewers_own_persona(actor: ObjectDB, presented: Persona) -> bool:
    """Whether ``presented`` is the persona the viewer themself is currently wearing."""
    from world.scenes.models import Persona  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    actor_sheet = resolve_actor_sheet(actor)
    if actor_sheet is None:
        return False
    try:
        viewer_persona = active_persona_for_sheet(actor_sheet)
    except Persona.DoesNotExist:
        return False
    return viewer_persona.pk == presented.pk


@dataclass
class IdentifiableTargetPrerequisite(Prerequisite):
    """The target must be present and currently presenting a fake-name persona (#1107 Task 3).

    Ruling 1a from Task 2's review (closing the overlay-only degenerate-SUCCESS hole): an
    overlay-only disguise (no persona swap — ``apply_disguise`` alone doesn't change
    ``active_persona_for_sheet``, see the Task 2 report's concern) or an undisguised target
    has nothing to identify and must fail here with a clean message, before
    ``attempt_identification`` is ever reached. (``attempt_identification``'s own
    presented-vs-true guard, ruling 1b, is defense-in-depth for a caller that skips this gate
    — e.g. a future non-Action caller of the service.)
    """

    def is_met(
        self,
        actor: ObjectDB,
        target: ObjectDB | None = None,
        context: dict | None = None,
    ) -> tuple[bool, str]:
        del target  # resolved from kwargs below — see _resolve_identify_target's docstring
        kwargs = (context or {}).get("kwargs", {})
        target_obj = _resolve_identify_target(kwargs)
        if target_obj is None:
            return False, _NO_TARGET_MESSAGE
        if target_obj.location != actor.location:
            return False, _NOT_PRESENT_MESSAGE

        presented = _presented_fake_persona(target_obj)
        if presented is None or _is_viewers_own_persona(actor, presented):
            return False, _NOTHING_TO_SEE_MESSAGE
        return True, ""


def _log_identify_attempt(actor: ObjectDB) -> None:
    """Log the attempt as a normal, outcome-blind scene Interaction (spec: "attempt is a scene
    action, normal Interaction visibility" — contains "silent stalking", per the issue #1107
    slice-5 leak-analysis table).

    Deliberately generic content — never names who was targeted, guessed, or revealed; the
    outcome stays roller-only via the returned ``ActionResult.message``. No-ops quietly when
    there's no active scene or persona to attribute it to (a defensive, non-fatal skip — the
    roll itself still proceeds either way).
    """
    from world.scenes.interaction_services import (  # noqa: PLC0415
        create_action_interaction_core,
        get_active_scene,
    )
    from world.scenes.models import Persona  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    sheet = resolve_actor_sheet(actor)
    if sheet is None:
        return
    scene = get_active_scene(actor.location)
    if scene is None:
        return
    try:
        persona = active_persona_for_sheet(sheet)
    except Persona.DoesNotExist:
        return
    create_action_interaction_core(
        persona=persona,
        scene=scene,
        summary_label="studies someone closely, trying to place who they really are.",
    )


@dataclass
class IdentifyAction(Action):
    """Try to see through a mask or disguise to who's really underneath (#1107 slice 5).

    Thin wrapper over ``attempt_identification`` (``world.forms.services.identification``),
    which owns the full check pipeline: difficulty, the roll, and the ``PersonaDiscovery``
    write. Result messaging is roller-only (never broadcast) — the oracle rule keeps FAILURE
    and AUTO_FAIL indistinguishable, and a BOTCH never reveals a real PC's name (it fake-IDs a
    random active ``Functionary`` instead).
    """

    key: str = "identify"
    name: str = "Identify"
    icon: str = "eye"
    category: str = "investigation"
    target_type: TargetType = TargetType.SINGLE
    target_kind: TargetKind | None = TargetKind.PERSONA
    target_filters: TargetFilters | None = field(
        default_factory=lambda: TargetFilters(in_same_scene=True, exclude_self=True)
    )
    action_category: ActionCategory | None = ActionCategory.MENTAL
    costs_turn: bool = True

    def get_prerequisites(self) -> list[Prerequisite]:
        return [IdentifiableTargetPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.forms.services.identification import attempt_identification  # noqa: PLC0415
        from world.forms.types import IdentificationOutcome  # noqa: PLC0415

        target = _resolve_identify_target(kwargs)
        if target is None:
            return ActionResult(success=False, message=_NO_TARGET_MESSAGE)

        guess = kwargs.get("guess")
        guess_name = str(guess).strip() if guess else None
        guess_name = guess_name or None

        _log_identify_attempt(actor)

        result = attempt_identification(actor, target, guess_name=guess_name)
        success = result.outcome == IdentificationOutcome.SUCCESS
        return ActionResult(success=success, message=result.player_message)
