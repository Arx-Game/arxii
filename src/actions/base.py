"""Base Action class — self-contained unit owning prerequisites, execution, and events."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from actions.prerequisites import Prerequisite
from actions.types import ActionAvailability, ActionContext, ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.constants import ActionCategory, TargetKind
    from actions.models import ActionEnhancement
    from actions.types import TargetFilters


@dataclass
class Action:
    """A self-contained action definition.

    Actions own their full lifecycle: prerequisites, intent event emission,
    execution, and result event emission. Commands (telnet) and the web
    dispatcher both call ``action.run()`` — the action handles everything.

    Subclasses override ``get_prerequisites()`` and ``execute()`` to define
    what the action checks and does.

    Attributes:
        key: Unique identifier for registry lookup (e.g., "look", "get").
        name: Human-readable name for UI display.
        icon: Icon identifier for frontend context menus.
        category: Grouping category (e.g., "perception", "combat").
        target_type: What kind of target this action operates on.
        intent_event: Event name emitted before execution (e.g., "before_look").
        result_event: Event name emitted after execution (e.g., "look").
        objectdb_target_kwargs: Names of kwargs whose ``*_id`` form (e.g., ``target_id``)
            should be resolved by the ``execute_action`` inputfunc from int → ObjectDB
            before dispatch. Names listed here are the *resolved* names — the inputfunc
            looks for ``<name>_id`` on the wire and passes ``<name>=<ObjectDB>`` to
            the action. Kwargs not listed here are passed through raw (so actions
            using non-ObjectDB pks like ``outfit_id`` are not eaten by the resolver).
            Default: empty — opt-in per action.
    """

    key: str
    name: str
    icon: str
    category: str
    target_type: TargetType
    target_kind: TargetKind | None = None
    target_filters: TargetFilters | None = None
    action_category: ActionCategory | None = None

    # Tempo: when True, dispatching this action inside an active scene round costs a
    # turn (triggers the round's resolution check / tick). Default False — pure utility
    # actions (look/say) never cost a turn. CHALLENGE/COMBAT backends are inherently
    # turn-costing and do not consult this flag. Spec: #520 §4.5.
    costs_turn: bool = False

    # Declarative resource cost (#1154): charged by ``run()`` before ``execute()``.
    # ``ap_cost`` spends Action Points — too few and the action fails without executing.
    # ``fatigue_cost`` adds fatigue to ``fatigue_category``'s pool (uncapped). Defaults of
    # 0 / None mean "free", so existing actions are unaffected; magnitudes are placeholder
    # data tuned in a later author pass (#1143).
    ap_cost: int = 0
    fatigue_cost: int = 0
    fatigue_category: str | None = None

    intent_event: str | None = None
    result_event: str | None = None

    objectdb_target_kwargs: ClassVar[frozenset[str]] = frozenset()

    def get_prerequisites(self) -> list[Prerequisite]:
        """Return the prerequisites that must be met for this action.

        Override in subclasses to define action-specific requirements.
        """
        return []

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        """Perform the action's core logic.

        Override in subclasses. Called after prerequisites pass and the
        intent event is not interrupted.

        Args:
            actor: The character performing the action.
            context: The mutable execution context (None for legacy callers).
            **kwargs: Action-specific parameters (target, text, etc.).

        Returns:
            Structured result of the action.
        """
        raise NotImplementedError

    def check_availability(
        self,
        actor: ObjectDB,
        target: ObjectDB | None = None,
        context: dict[str, Any] | None = None,
    ) -> ActionAvailability:
        """Evaluate all prerequisites. Return availability with reasons.

        Args:
            actor: The character who would perform the action.
            target: Optional target of the action.
            context: Optional situational context (combat, scene, etc.).
        """
        failures = []
        for prereq in self.get_prerequisites():
            met, reason = prereq.is_met(actor, target, context)
            if not met:
                failures.append(reason)
        return ActionAvailability(
            action_key=self.key,
            available=len(failures) == 0,
            reasons=failures,
        )

    def _charge_costs(self, actor: ObjectDB) -> ActionResult | None:
        """Charge the action's declarative AP + fatigue cost (#1154).

        Returns a failure ``ActionResult`` when the actor cannot afford the AP cost
        (the action then does not execute); otherwise charges and returns ``None``.
        Fatigue is uncapped, so it always applies once the AP cost is paid.
        """
        if self.ap_cost > 0:
            from world.action_points.models import ActionPointPool  # noqa: PLC0415

            pool = ActionPointPool.get_or_create_for_character(actor)
            if not pool.spend(self.ap_cost):
                return ActionResult(
                    success=False,
                    message="You don't have enough action points for that.",
                )
        if self.fatigue_cost > 0 and self.fatigue_category is not None:
            from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

            from world.fatigue.constants import EffortLevel  # noqa: PLC0415
            from world.fatigue.services import apply_fatigue  # noqa: PLC0415

            try:
                sheet = actor.sheet_data
            except (AttributeError, ObjectDoesNotExist):
                sheet = None
            if sheet is not None:
                apply_fatigue(sheet, self.fatigue_category, self.fatigue_cost, EffortLevel.MEDIUM)
        return None

    def run(
        self,
        actor: ObjectDB,
        enhancements: list[ActionEnhancement] | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        """Full lifecycle: build context -> apply enhancements -> execute -> post-effects.

        This is the primary entry point. Both commands (telnet) and the
        web action dispatcher call this method.

        Args:
            actor: The character performing the action.
            enhancements: Voluntary enhancements chosen by the player.
            **kwargs: Action-specific parameters (target, text, etc.).

        Returns:
            Structured result of the action.
        """
        from actions.enhancements import get_involuntary_enhancements  # noqa: PLC0415
        from flows.scene_data_manager import SceneDataManager  # noqa: PLC0415

        # Build context
        sdm = SceneDataManager()
        sdm.initialize_state_for_object(actor)
        context = ActionContext(
            action=self,
            actor=actor,
            target=kwargs.get("target"),
            kwargs=kwargs,
            scene_data=sdm,
        )

        # Apply voluntary enhancements (chosen by player)
        for enh in enhancements or []:
            enh.apply(context)

        # Query and apply involuntary enhancements
        for enh in get_involuntary_enhancements(self.key, actor):
            enh.apply(context)

        # TODO: emit intent event and check for trigger interruption

        # Enforce prerequisites against the final (post-enhancement) kwargs.
        # run() is the single telnet+web chokepoint; prerequisites read kwargs
        # via the context dict (so they can see a second target).
        availability = self.check_availability(
            actor,
            target=context.kwargs.get("target"),
            context={"kwargs": context.kwargs, "scene_data": sdm},
        )
        if not availability.available:
            return ActionResult(
                success=False,
                message="; ".join(availability.reasons) or "You can't do that right now.",
            )

        # Charge the action's declarative AP + fatigue cost before executing (#1154).
        cost_failure = self._charge_costs(actor)
        if cost_failure is not None:
            return cost_failure

        # Execute with potentially modified kwargs
        context.result = self.execute(actor, context=context, **context.kwargs)

        # Run post-effects
        for effect in context.post_effects:
            effect(context)

        # TODO: emit result event for trigger reactions

        return context.result
