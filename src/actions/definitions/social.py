"""Social action singletons — registry-backed dispatch for ActionTemplate social actions (#544).

Each singleton exposes ``target_kind = TargetKind.PERSONA`` so the frontend knows
to prompt for a persona target. The ``execute()`` path goes through
``start_action_resolution`` which resolves the linked ActionTemplate's check chain.

These are real ``Action`` subclasses (#1172): the registry dispatch path and the
scene consent path both rely on the ``Action`` interface (``run()`` / ``execute()`` /
``dispatch_effects()``). Inherent target effects (e.g. RestoreSense removing a
Berserk condition) live in ``dispatch_effects`` so they fire exactly once whether
the action is driven through ``run()`` or through the scene consent resolution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.constants import ActionCategory, TargetKind
from actions.types import TargetFilters, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.models import ActionTemplate
    from actions.types import ActionContext, ActionResult, PendingActionResolution
    from flows.scene_data_manager import SceneDataManager


@dataclass
class _SocialTemplateAction(Action):
    """Base for social ActionTemplate-driven actions.

    Subclasses set ``key``, ``name``, ``icon``, and ``template_name``. The
    common social defaults (PERSONA single target, social category, turn cost)
    are supplied here so concrete classes only declare what differs.
    """

    category: str = "social"
    target_type: TargetType = TargetType.SINGLE
    target_kind: TargetKind | None = TargetKind.PERSONA
    target_filters: TargetFilters | None = field(
        default_factory=lambda: TargetFilters(in_same_scene=True, exclude_self=True)
    )
    action_category: ActionCategory | None = ActionCategory.SOCIAL
    costs_turn: bool = True

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        _template, result = self._resolve_template(actor, context, **kwargs)
        return result

    def _resolve_template(
        self,
        actor: ObjectDB,
        context: ActionContext | None,
        **kwargs: Any,
    ) -> tuple[ActionTemplate, ActionResult]:
        """Resolve this action's ActionTemplate and wrap the outcome into an ``ActionResult``.

        Shared by the base ``execute()`` and ``EntranceAction.execute()`` (which needs the
        ``ActionTemplate`` afterward to decide the entry-flourish offer). Dispatches inherent
        target effects first (no-op for plain social actions; RestoreSense removes Berserk).
        On this path a single dispatch only runs through ``execute()``, never the consent
        path too.
        """
        from actions.models import ActionTemplate  # noqa: PLC0415
        from actions.services import start_action_resolution  # noqa: PLC0415
        from world.checks.types import ResolutionContext  # noqa: PLC0415

        scene_data = context.scene_data if context is not None else None
        self.dispatch_effects(actor, kwargs.get("target"), scene_data)

        template = ActionTemplate.objects.get(name=self.template_name)
        resolution_ctx = ResolutionContext(character=actor, action_context=context)
        resolution = start_action_resolution(
            character=actor,
            template=template,
            target_difficulty=0,
            context=resolution_ctx,
        )
        return template, self._result_from_resolution(resolution)

    @staticmethod
    def _result_from_resolution(
        resolution: PendingActionResolution, message: str | None = None
    ) -> ActionResult:
        """Wrap a ``PendingActionResolution`` into the ``ActionResult`` its consumers expect.

        ``execute()``'s only live consumers are REGISTRY ones — the telnet command
        (reads ``.message``) and the web dispatcher (stuffs the result into
        ``DispatchResult.detail``, typed ``ActionResult``). The rich pending-resolution
        object is consumed elsewhere by direct callers of ``start_action_resolution``
        (scene consent, cast), never through here — so returning an ``ActionResult`` is
        both honest and what these consumers actually read (#1245). Success is the one
        canonical expression every resolution consumer uses
        (``main_result.check_result.success_level``); ``main_result is None`` is a
        *paused* resolution whose main step hasn't rolled, so it cannot have succeeded.
        The full resolution rides ``data`` so nothing is lost.
        """
        from actions.types import ActionResult as _ActionResult  # noqa: PLC0415

        main = resolution.main_result
        succeeded = main is not None and main.check_result.success_level > 0
        return _ActionResult(success=succeeded, message=message, data={"resolution": resolution})


@dataclass
class IntimidateAction(_SocialTemplateAction):
    key: str = "intimidate"
    name: str = "Intimidate"
    icon: str = "skull"
    template_name: str = "Intimidate"
    description: str = "Coerce through force of presence, threats, or physical dominance."


@dataclass
class PersuadeAction(_SocialTemplateAction):
    key: str = "persuade"
    name: str = "Persuade"
    icon: str = "handshake"
    template_name: str = "Persuade"
    description: str = "Convince through reasoned argument, charm, and social grace."


@dataclass
class DeceiveAction(_SocialTemplateAction):
    key: str = "deceive"
    name: str = "Deceive"
    icon: str = "mask"
    template_name: str = "Deceive"
    description: str = "Mislead through misdirection, half-truths, or outright lies."


@dataclass
class FlirtAction(_SocialTemplateAction):
    key: str = "flirt"
    name: str = "Flirt"
    icon: str = "heart"
    template_name: str = "Flirt"
    description: str = "Beguile through charm, allure, and romantic suggestion."


@dataclass
class PerformAction(_SocialTemplateAction):
    key: str = "perform"
    name: str = "Perform"
    icon: str = "music"
    template_name: str = "Perform"
    description: str = "Captivate an audience through music, oration, or storytelling."


@dataclass
class EntranceAction(_SocialTemplateAction):
    key: str = "entrance"
    name: str = "Entrance"
    icon: str = "sparkles"
    template_name: str = "Entrance"
    description: str = "Command attention through sheer force of personality on entering."

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        template, result = self._resolve_template(actor, context, **kwargs)

        # On a SUCCESSFUL entrance, open the entry-flourish offer (actor self-grant)
        # and prompt the actor toward declaring it. The prompt rides the result
        # ``message`` like every other action — the command surfaces it via
        # ``self.msg(result.message)`` and the web dispatcher via ``detail.message`` (#1245).
        if template.grants_entry_flourish and result.success:
            from world.magic.entry_flourish import (  # noqa: PLC0415
                maybe_create_entry_flourish_offer,
            )

            loc = actor.location
            scene = loc.active_scene if loc is not None and hasattr(loc, "active_scene") else None
            offer = maybe_create_entry_flourish_offer(actor, scene)
            if offer is not None:
                prompt = "Use |wflourish <resonance>|n to declare your entrance."
                result.message = f"{result.message}\n{prompt}" if result.message else prompt

        return result


@dataclass
class RestoreSenseAction(_SocialTemplateAction):
    key: str = "restore_sense"
    name: str = "Restore to Sense"
    icon: str = "heart-pulse"
    template_name: str = "Restore to Sense"
    description: str = "Talk a berserk ally down through force of personality and connection."

    def dispatch_effects(
        self,
        actor: ObjectDB,
        target: ObjectDB | None = None,
        scene_data: SceneDataManager | None = None,
    ) -> None:
        """Dispatch the RemoveConditionOnCheckConfig wired to ``restore_sense``.

        The factory seeds a ``RemoveConditionOnCheckConfig`` on an
        ``ActionEnhancement`` keyed ``base_action_key="restore_sense"``;
        ``apply_effects`` dispatches it to ``handle_remove_condition_on_check``,
        which rolls a check against *target* and removes the Berserk condition on
        success. Called by ``execute()`` (registry/``run()`` path) and by the
        scene consent resolution.
        """
        from actions.effects.registry import apply_effects  # noqa: PLC0415
        from actions.models import ActionEnhancement  # noqa: PLC0415
        from actions.types import (  # noqa: PLC0415
            ActionContext as _ActionContext,
            ActionResult as _ActionResult,
        )
        from flows.scene_data_manager import SceneDataManager  # noqa: PLC0415

        sdm = scene_data
        if sdm is None:
            sdm = SceneDataManager()
            sdm.initialize_state_for_object(actor)

        effect_ctx = _ActionContext(
            action=self,
            actor=actor,
            target=target,
            kwargs={},
            scene_data=sdm,
            result=_ActionResult(success=True),
        )

        for enh in ActionEnhancement.objects.filter(base_action_key=self.key):
            apply_effects(enh, effect_ctx)


@dataclass
class ResolveFlourishOfferAction(Action):
    """Resolve a pending entry-flourish offer by declaring a resonance."""

    key: str = "resolve_entry_flourish"
    name: str = "Declare Flourish"
    icon: str = "sparkles"
    category: str = "social"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        *,
        offer: object,
        resonance: object,
        **kwargs: Any,
    ) -> ActionResult:
        from actions.types import ActionResult as _ActionResult  # noqa: PLC0415
        from world.magic.entry_flourish import resolve_entry_flourish_offer  # noqa: PLC0415
        from world.magic.exceptions import (  # noqa: PLC0415
            EntryFlourishOfferNotFoundError,
            EntryFlourishOfferStaleError,
        )

        try:
            entry_result = resolve_entry_flourish_offer(offer, resonance=resonance)
        except EntryFlourishOfferNotFoundError:
            return _ActionResult(success=False, message="You have no pending flourish offer.")
        except EntryFlourishOfferStaleError:
            return _ActionResult(
                success=False,
                message="That resonance is no longer yours to broadcast.",
            )
        return _ActionResult(
            success=True,
            message=(
                f"Your {entry_result.resonance_name} fills the room as you announce your arrival."
            ),
            data={"entry_flourish_result": entry_result},
        )


# Module-level singletons — registered in actions/registry.py
intimidate = IntimidateAction()
persuade = PersuadeAction()
deceive = DeceiveAction()
flirt = FlirtAction()
perform = PerformAction()
entrance = EntranceAction()
restore_sense = RestoreSenseAction()
resolve_entry_flourish = ResolveFlourishOfferAction()
