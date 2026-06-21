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
                matched_pks = self._validate_components(ritual, components)
                self._consume(matched_pks)

                if ritual.execution_kind == RitualExecutionKind.SERVICE:
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
        ) as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(
            success=True,
            message=f"You perform {ritual.name}.",
            data={"execution_kind": ritual.execution_kind, "result": result},
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_components(self, ritual: Any, components: list[Any]) -> list[int]:
        """Check that ``components`` satisfy all of the ritual's requirements.

        Delegates to ``gather_consumable_pks``, translating
        ``InsufficientMaterials`` into the ritual-surface ``RitualComponentError``.
        """
        from world.items.exceptions import InsufficientMaterials  # noqa: PLC0415
        from world.items.services.materials import gather_consumable_pks  # noqa: PLC0415
        from world.magic.exceptions import RitualComponentError  # noqa: PLC0415

        requirements = ritual.requirements.all().select_related("item_template", "min_quality_tier")
        try:
            return gather_consumable_pks(available=components, requirements=requirements)
        except InsufficientMaterials as exc:
            req = exc.requirement
            msg = (
                f"Ritual '{ritual.name}' requires {req.quantity}x "
                f"'{req.item_template}' but only {exc.provided_qty} provided."
            )
            raise RitualComponentError(msg) from exc

    def _consume(self, matched_pks: list[int]) -> None:
        """Atomically consume the matched component instances."""
        from world.items.services.materials import consume_pks  # noqa: PLC0415

        consume_pks(matched_pks)

    def _dispatch_service(self, ritual: Any, sheet: Any, kwargs: dict[str, Any]) -> Any:
        """Import and call the ritual's service function.

        Convention: the service functions take ``character_sheet=`` as their
        first kwarg (e.g. ``spend_resonance_for_imbuing``), not ``actor=``.
        """
        import importlib  # noqa: PLC0415

        module_path, func_name = ritual.service_function_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        func = getattr(module, func_name)
        return func(character_sheet=sheet, **kwargs)

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
