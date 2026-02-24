"""handlers.py: generic, parameter-driven command handler

A handler instance is created by the dispatcher with two constructor
arguments:

    flow_name           the FlowDefinition to run once prerequisites pass
    prerequisite_events an iterable of event names to emit first

The dispatcher resolves every game object mentioned in the player's input and
calls something like:

    handler.run(caller=<ObjectDB>, target=<ObjectDB>, amount=5, ...)

All keyword arguments become *flow variables* **unaltered**.  If a variable is an
Evennia object the instance is passed through intact, so service functions and
flow steps still have full access to its methods and cached properties.
"""

from collections.abc import Mapping, Sequence

from evennia.objects.models import ObjectDB

from commands.exceptions import CommandError
from flows.consts import FlowState
from flows.flow_stack import FlowStack
from flows.models import FlowDefinition
from flows.scene_data_manager import SceneDataManager

__all__ = ["BaseHandler"]


NO_FLOW_ERR = "No flow stack found."
NO_CONTEXT_ERR = "No context found."


class BaseHandler:
    """Run prerequisite mini-flows, then the main flow specified by *flow_name*."""

    # ---------------------------------------------------------------------
    # Construction
    # ---------------------------------------------------------------------
    def __init__(
        self,
        *,
        flow_name: str,
        prerequisite_events: Sequence[str] | None = None,
    ) -> None:
        if not flow_name:
            msg = "flow_name is required"
            raise ValueError(msg)

        self.flow_name: str = flow_name
        self.prerequisite_events: tuple[str, ...] = tuple(prerequisite_events or ())

        # Will be assigned in _prime_context
        self.context: SceneDataManager | None = None
        self.flow_stack: FlowStack | None = None

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def run(self, **dispatcher_vars: object) -> None:
        """Prime context, run prerequisites, then run the main flow."""
        caller = dispatcher_vars.get("caller")
        if not isinstance(caller, ObjectDB):
            msg = "caller is required in dispatcher_vars"
            raise ValueError(msg)
        self.flow_stack = FlowStack(trigger_registry=caller.trigger_registry)
        self._prime_context(caller=caller, flow_vars=dispatcher_vars)
        self._run_prerequisites()
        self._run_main_flow(caller=caller, flow_vars=dispatcher_vars)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _prime_context(self, *, caller: ObjectDB, flow_vars: Mapping[str, object]) -> None:
        """Add ObjectState entries for *caller* and any object-typed flow variable."""
        self.context = caller.location.scene_data
        self.context.initialize_state_for_object(caller)

        for value in flow_vars.values():
            if isinstance(value, ObjectDB):
                self.context.initialize_state_for_object(value)

    # ------------------------------------------------------------------
    def _run_prerequisites(self) -> None:
        """Emit each prerequisite event via a one-step flow and honour stops."""
        for event_name in self.prerequisite_events:
            prerequisite_def = self._emit_event_flow_definition(event_name)
            if not self.flow_stack or not self.context:
                raise RuntimeError(NO_FLOW_ERR)
            prerequisite_exec = self.flow_stack.create_and_execute_flow(
                prerequisite_def,
                context=self.context,
                origin=self,
                variable_mapping={},
            )
            if prerequisite_exec.state is FlowState.STOP:
                message: str = prerequisite_exec.stop_reason or "Action not permitted."
                raise CommandError(message)

    # Helper: build a minimal FlowDefinition that simply emits *event_name*
    @staticmethod
    def _emit_event_flow_definition(event_name: str) -> FlowDefinition:
        return FlowDefinition.emit_event_definition(event_name)

    # ------------------------------------------------------------------
    def _run_main_flow(
        self,
        *,
        caller: ObjectDB,
        flow_vars: Mapping[str, object],
    ) -> None:
        """Look up *flow_name* and execute it on the current FlowStack."""
        try:
            main_flow_def = FlowDefinition.objects.get(name=self.flow_name)
        except FlowDefinition.DoesNotExist as exc:  # pragma: no cover
            msg = f"Flow '{self.flow_name}' not found."
            raise CommandError(msg) from exc

        # Inject caller for convenience so flow steps can refer to it.
        initial_vars: dict[str, object] = {"caller": caller, **flow_vars}

        if not self.flow_stack or not self.context:
            raise RuntimeError(NO_FLOW_ERR)
        self.flow_stack.create_and_execute_flow(
            main_flow_def,
            context=self.context,
            origin=self,
            variable_mapping=initial_vars,
        )
