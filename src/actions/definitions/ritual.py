"""Ritual performance action — the action.run() seam for SERVICE/FLOW rituals.

`PerformRitualAction` composes component validation, atomic consumption, and
dual dispatch (SERVICE → service function; FLOW → FlowDefinition) into a single
`Action`. Both telnet (`commands.ritual.CmdRitual`) and the web
(`world.magic.views.RitualPerformView`) converge on this action's `run()`, so
ritual performance no longer bypasses the action layer (G3 closure, #1331).

All `world.magic` / `world.items` imports are done lazily inside `execute()` to
avoid import cycles (the action registry is imported very early; magic models
pull in much of the world graph).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext


@dataclass
class PerformRitualAction(Action):
    """Validate components, consume them, and dispatch a ritual.

    Dispatch kinds in scope: SERVICE (imports + calls a service function with
    ``character_sheet=`` + the ritual kwargs) and FLOW (runs the ritual's
    ``FlowDefinition``). Known ritual-surface exceptions are caught and returned
    as a failure ``ActionResult`` so both telnet (prints ``message``) and web
    (maps ``message`` → HTTP 400) get a uniform, user-safe failure.

    kwargs:
        ritual: The ``Ritual`` to perform (required).
        components_provided: ``ItemInstance`` rows the actor contributes;
            pruned to the minimum the ritual needs. Default ``[]``.
        **kwargs: Forwarded to the service function / flow (e.g. ``thread``).
    """

    key: str = "perform_ritual"
    name: str = "Perform Ritual"
    icon: str = "sparkles"
    category: str = "magic"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        """Perform the ritual, returning a structured result."""
        from django.db import transaction  # noqa: PLC0415

        from world.magic.constants import RitualExecutionKind  # noqa: PLC0415
        from world.magic.exceptions import (  # noqa: PLC0415
            AnchorCapExceeded,
            GhostTutorError,
            InvalidImbueAmount,
            ResonanceInsufficient,
            RitualComponentError,
            XPInsufficient,
        )

        ritual = kwargs.pop("ritual", None)
        if ritual is None:
            return ActionResult(success=False, message="Perform which ritual?")

        components = kwargs.pop("components_provided", [])
        sheet = actor.sheet_data

        try:
            with transaction.atomic():
                self._validate_components(ritual, components, sheet)

                if ritual.execution_kind == RitualExecutionKind.CEREMONY:
                    result = self._begin_ceremony(ritual, sheet)
                elif ritual.execution_kind == RitualExecutionKind.SERVICE:
                    result = self._dispatch_service(ritual, sheet, kwargs)
                else:
                    self._dispatch_flow(ritual, sheet, kwargs)
                    result = None
        except (
            RitualComponentError,
            ResonanceInsufficient,
            AnchorCapExceeded,
            InvalidImbueAmount,
            XPInsufficient,
            GhostTutorError,
        ) as exc:
            return ActionResult(success=False, message=exc.user_message)

        msg = (
            f"You begin {ritual.name}."
            if ritual.execution_kind == RitualExecutionKind.CEREMONY
            else f"You perform {ritual.name}."
        )
        return ActionResult(
            success=True,
            message=msg,
            data={"execution_kind": ritual.execution_kind, "result": result},
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_components(
        self, ritual: Any, components: list[Any], performer_sheet: Any
    ) -> None:
        """Validate and consume ``ritual``'s components via the shared helper."""
        from world.magic.services.ritual_components import (  # noqa: PLC0415
            resolve_and_consume_ritual_components,
        )

        resolve_and_consume_ritual_components(
            ritual=ritual, components=components, performer_sheet=performer_sheet
        )

    def _dispatch_service(self, ritual: Any, sheet: Any, kwargs: dict[str, Any]) -> Any:
        """Import and call the ritual's service function.

        Convention: the service functions take ``character_sheet=`` as their
        first kwarg (e.g. ``spend_resonance_for_imbuing``), not ``actor=``.
        The ``ritual`` instance is also forwarded so service functions that
        need to resolve authored data linked to the ritual (e.g. a
        ``TechniqueGrant``) can do so. Service functions should accept
        ``**kwargs`` to absorb parameters they don't use.
        """
        import importlib  # noqa: PLC0415

        module_path, func_name = ritual.service_function_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        func = getattr(module, func_name)
        return func(character_sheet=sheet, ritual=ritual, **kwargs)

    def _begin_ceremony(self, ritual: Any, sheet: Any) -> Any:
        """Create a PendingRitualEffect for a CEREMONY-kind ritual.

        Raises RitualComponentError (with a dynamic user_message) if a pending
        effect already exists — caught by the caller's except block.
        """
        from world.magic.exceptions import RitualComponentError  # noqa: PLC0415
        from world.magic.models import PendingRitualEffect  # noqa: PLC0415

        if PendingRitualEffect.objects.filter(character=sheet, ritual=ritual).exists():
            exc = RitualComponentError()
            exc.user_message = f"A {ritual.name} is already in progress."
            raise exc
        return PendingRitualEffect.objects.create(character=sheet, ritual=ritual)

    def _dispatch_flow(self, ritual: Any, sheet: Any, kwargs: dict[str, Any]) -> None:
        """Execute the ritual's FlowDefinition via a manual FlowExecution run."""
        from flows.flow_execution import FlowExecution  # noqa: PLC0415
        from flows.flow_stack import FlowStack  # noqa: PLC0415
        from flows.scene_data_manager import SceneDataManager  # noqa: PLC0415
        from flows.trigger_handler import DispatchResult  # noqa: PLC0415

        stack = FlowStack(owner=sheet, originating_event="RitualPerformed")
        flow_context = SceneDataManager()
        execution = FlowExecution(
            flow_definition=ritual.flow,
            context=flow_context,
            flow_stack=stack,
            origin=None,
            variable_mapping={"actor": sheet, **kwargs},
            dispatch_result=DispatchResult(),
        )
        stack.execute_flow(execution)
