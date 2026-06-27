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
    from flows.scene_data_manager import SceneDataManager


@dataclass
class Action:
    """A self-contained action definition.

    Actions own their full lifecycle: prerequisites, intent event emission,
    execution, and result event emission.

    ``action.run()`` is the entry point for the **REGISTRY** path only.  Plain
    telnet :class:`~commands.command.ArxCommand` s call it directly; the web
    frontend and telnet :class:`~commands.command.DispatchCommand` s instead call
    ``dispatch_player_action()``, which routes by backend: REGISTRY →
    ``action.run()``, CHALLENGE → ``resolve_challenge()``, COMBAT →
    ``declare_action()``/``resolve_round()``.  Magic and combat actions never
    reach ``action.run()`` directly.

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

    # Name of the ActionTemplate this action resolves through, if any. Set by
    # registry-backed, data-driven actions (the social actions) so the scene
    # layer can map a request's ``action_key`` back to its ActionTemplate — an
    # ActionTemplate has only a unique ``name``, no key/slug column (#1172).
    # Empty for actions that are not ActionTemplate-backed.
    template_name: str = ""

    objectdb_target_kwargs: ClassVar[frozenset[str]] = frozenset()

    def get_prerequisites(self) -> list[Prerequisite]:
        """Return the prerequisites that must be met for this action.

        Override in subclasses to define action-specific requirements.
        """
        return []

    def round_declaration(
        self, ctx: Any, **kwargs: Any
    ) -> tuple[Any, dict[str, Any]] | ActionResult | None:
        """Return (PlayerAction, dispatch_kwargs) to defer, ActionResult to short-circuit, or None.

        - ``tuple[PlayerAction, dict]``: record the declaration and return deferred=True.
        - ``ActionResult``: short-circuit (e.g. soulfray gate) — return the result message,
          do NOT record a declaration or call execute().
        - ``None``: fall through to immediate execute().
        """
        return None

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

    def dispatch_effects(
        self,
        actor: ObjectDB,
        target: ObjectDB | None = None,
        scene_data: SceneDataManager | None = None,
    ) -> None:
        """Dispatch this action's inherent, target-gated effect configs.

        Default no-op. Actions with built-in effects (e.g. the social
        ``RestoreSenseAction`` removing a Berserk condition) override this to
        dispatch their ``ActionEnhancement`` effect configs against *target*.

        Called from two places so the effects fire exactly once regardless of
        dispatch route: the action's own ``execute()`` (the registry/``run()``
        path) and the scene consent resolution (``_resolve_action_against_persona``
        in ``world.scenes.action_services``), which resolves the check chain
        directly and never reaches ``execute()``. A single live dispatch only
        ever travels one of those routes, so there is no double-application.
        """

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
        actor: ObjectDB | None,
        enhancements: list[ActionEnhancement] | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        """Full lifecycle: build context -> apply enhancements -> execute -> post-effects.

        This is the primary entry point. Both commands (telnet) and the
        web action dispatcher call this method.

        ``actor`` is the character performing the action and may be ``None``
        for **account-authorized** actions that need no character context —
        e.g. a staffer or scene-GM managing an event they do not own (the
        host/GM/staff gate is account-based, mirroring the DRF permission
        classes). When ``actor`` is ``None`` the character-scoped machinery
        (scene-state init, involuntary enhancements) is skipped: those are
        character-scoped and have nothing to apply to an account-only caller.
        Character-acting actions (create/respond) always supply an actor.

        Args:
            actor: The character performing the action, or ``None`` for
                account-authorized actions with no character context.
            enhancements: Voluntary enhancements chosen by the player.
            **kwargs: Action-specific parameters (target, text, etc.).

        Returns:
            Structured result of the action.
        """
        from actions.enhancements import get_involuntary_enhancements  # noqa: PLC0415
        from flows.scene_data_manager import SceneDataManager  # noqa: PLC0415

        # Build context
        sdm = SceneDataManager()
        if actor is not None:
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

        # Query and apply involuntary enhancements (character-scoped — none to
        # apply when there is no actor, e.g. an account-authorized event action).
        if actor is not None:
            for enh in get_involuntary_enhancements(self.key, actor):
                enh.apply(context)

        # TODO: emit intent event and check for trigger interruption

        # Enforce prerequisites against the final (post-enhancement) kwargs.
        # run() is the single telnet+web chokepoint; prerequisites read kwargs
        # via the context dict (so they can see a second target). Account-
        # authorized actions (actor is None) have no character-scoped
        # prerequisites, so skip the gate for them.
        if actor is not None:
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
        # Account-authorized actions have no AP/fatigue cost and no actor to
        # charge against; skip for them.
        if actor is not None:
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
