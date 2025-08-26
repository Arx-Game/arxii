from typing import TYPE_CHECKING, Callable, Optional, cast

from flows.consts import FlowState
from flows.models import FlowDefinition, FlowStepDefinition
from flows.object_states.base_state import BaseState
from flows.scene_data_manager import SceneDataManager
from flows.trigger_registry import TriggerRegistry
from typeclasses.objects import Object

if TYPE_CHECKING:
    from flows.flow_stack import FlowStack


class FlowExecution:
    """Runtime instance of a flow definition.

    A FlowExecution loads all steps for its definition and tracks which one is
    currently running. Variables used by the flow are stored in
    `variable_mapping` and may be filled by triggers or previous steps.
    Service functions referenced by steps are resolved from the
    `service_functions` module.

    FlowExecution works with SceneDataManager to manage ephemeral object states and
    with FlowStack to orchestrate nested flows. Keeping logic in the database
    allows designers to iterate on behavior without modifying Python code.
    """

    def __init__(
        self,
        flow_definition: FlowDefinition,
        context: SceneDataManager,
        flow_stack: "FlowStack",
        origin: Object,
        variable_mapping: Optional[dict[str, object]] = None,
        trigger_registry: Optional[TriggerRegistry] = None,
    ) -> None:
        """Initialize a FlowExecution instance.

        Args:
            flow_definition: The flow definition to execute.
            context: Shared SceneDataManager for this execution.
            flow_stack: FlowStack orchestrating nested flows.
            origin: Object that initiated the flow.
            variable_mapping: Initial mapping of variable names to values.
            trigger_registry: Registry used when emitting events.
        """
        self.flow_definition = flow_definition
        self.context = context
        self.flow_stack = flow_stack
        self.origin = origin
        self.state: FlowState = FlowState.RUNNING
        self.stop_reason: str | None = None
        self.variable_mapping = (
            variable_mapping or {}
        )  # Maps flow variable names to their values
        self.trigger_registry = trigger_registry or flow_stack.trigger_registry
        self.steps = list(flow_definition.steps.all())
        self.current_step = self._get_entry_step()

    def _get_entry_step(self) -> FlowStepDefinition:
        """Finds and returns the entry step (the step with no parent)."""
        for step in self.steps:
            if step.parent_id is None:
                return cast(FlowStepDefinition, step)
        raise RuntimeError(
            f"No entry step found for FlowDefinition '{self.flow_definition.name}'."
        )

    def execute_current_step(self) -> None:
        """
        Executes the current step using the flow execution as context,
        and updates the current step to the next one.
        """
        if not self.current_step:
            return  # Flow is complete
        next_step = self.current_step.execute(self)
        self.current_step = next_step

    def get_variable(self, var_name: str) -> Optional[object]:
        """Retrieve the value of a flow variable from this execution's mapping."""
        return self.variable_mapping.get(var_name)

    def resolve_flow_reference(self, value: object) -> object:
        """Resolve a value that may reference a flow variable.

        If `value` begins with `@` it is treated as a variable name and may
        use dot notation to access nested attributes. Otherwise the value is
        returned unchanged.

        Args:
            value: String or object to resolve.

        Returns:
            The resolved object or original value.

        Raises:
            RuntimeError: If the variable or attribute does not exist.
        """
        if isinstance(value, str) and value.startswith("@"):
            path = value[1:].split(".")
            base = self.get_variable(path[0])
            if base is None:
                raise RuntimeError(f"Flow variable '{path[0]}' is undefined.")
            current = base
            for attr in path[1:]:
                if isinstance(current, dict):
                    current = current.get(attr)
                else:
                    current = getattr(current, attr, None)
                if current is None:
                    raise RuntimeError(f"Attribute '{attr}' not found on {base}.")
            return current
        return value

    def set_variable(self, var_name: str, value: object) -> None:
        """Set the value of a flow variable in this execution's mapping."""
        self.variable_mapping[var_name] = value

    def get_object_state(self, obj_ref: object) -> Optional[BaseState]:
        """Return a BaseState for ``obj_ref`` if possible.

        ``obj_ref`` may be a flow variable reference, an Evennia object,
        a primary key, or an existing BaseState. The method resolves any
        variable references and then attempts to look up the corresponding state
        in the current SceneDataManager.

        Args:
            obj_ref: Reference to resolve into a state.

        Returns:
            A BaseState instance or ``None`` if no state could be found.
        """

        resolved = self.resolve_flow_reference(obj_ref)

        if isinstance(resolved, BaseState):
            return resolved
        try:
            pk = resolved.pk  # type: ignore[attr-defined]
        except AttributeError:
            pk = resolved
        return cast(Optional[BaseState], self.context.get_state_by_pk(pk))

    def get_service_function(self, function_name: str) -> Callable:
        """Return a service function by name."""
        from flows import service_functions

        return service_functions.get_service_function(function_name)

    def get_next_child(
        self, current_step: FlowStepDefinition
    ) -> Optional[FlowStepDefinition]:
        """Return the first child of ``current_step`` if any."""
        for step in self.steps:
            if step.parent_id == current_step.id:
                return cast(FlowStepDefinition, step)
        return None

    def get_next_sibling(
        self, current_step: FlowStepDefinition
    ) -> Optional[FlowStepDefinition]:
        """Return the next sibling of ``current_step`` if any."""
        if not current_step.parent_id:
            return None
        siblings = [s for s in self.steps if s.parent_id == current_step.parent_id]
        idx = siblings.index(current_step)
        return siblings[idx + 1] if idx + 1 < len(siblings) else None

    def execution_key(self) -> str:
        """Return a unique key for this execution based on the definition and origin."""
        return f"{self.flow_definition.id}:{str(self.origin)}"

    def get_trigger_registry(self) -> Optional[TriggerRegistry]:
        """Return the TriggerRegistry for the current execution."""
        return self.trigger_registry
