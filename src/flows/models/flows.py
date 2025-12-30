from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Optional, cast

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from flows.consts import OPERATOR_MAP, FlowActionChoices
from flows.flow_event import FlowEvent
from flows.helpers.logic import resolve_modifier

if TYPE_CHECKING:
    from flows.flow_execution import FlowExecution

CONDITIONAL_ACTIONS = {
    FlowActionChoices.EVALUATE_EQUALS,
    FlowActionChoices.EVALUATE_NOT_EQUALS,
    FlowActionChoices.EVALUATE_LESS_THAN,
    FlowActionChoices.EVALUATE_GREATER_THAN,
    FlowActionChoices.EVALUATE_LESS_THAN_OR_EQUALS,
    FlowActionChoices.EVALUATE_GREATER_THAN_OR_EQUALS,
}


class FlowDefinition(SharedMemoryModel):
    """Represents a reusable definition for a flow, consisting of multiple steps."""

    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True, null=True)
    if TYPE_CHECKING:
        steps: "models.Manager[FlowStepDefinition]"
        _unsaved_steps: list["FlowStepDefinition"]

    def __str__(self) -> str:
        return str(self.name)

    @staticmethod
    def emit_event_definition(event_name: str) -> "FlowDefinition":
        """Create an unsaved FlowDefinition that emits ``event_name``."""
        flow_def = FlowDefinition(name=f"_emit_{event_name}")
        step = FlowStepDefinition(
            flow=flow_def,
            action=FlowActionChoices.EMIT_FLOW_EVENT,
            variable_name="emit_event",
            parameters={"event_type": event_name},
        )
        flow_def._unsaved_steps = [step]
        flow_def.steps = cast(Any, SimpleNamespace(all=lambda: flow_def._unsaved_steps))
        return flow_def


class FlowStepDefinition(SharedMemoryModel):
    """Represents a single step in a flow definition.

    The ``variable_name`` field is a generic reference whose meaning depends on
    the action:
      - For conditional steps, it names the flow variable to test.
      - For ``SET_CONTEXT_VALUE``, it indicates which context variable to set.
      - For ``CALL_SERVICE_FUNCTION``, it names the service function or lookup
        key.

    The ``parameters`` JSONField stores action-specific data. For a condition it
    might be ``{"value": "10"}`` while for a service function it could be a
    mapping of keyword arguments such as ``{"modifier": "5", "result_variable":
    "attack_result"}``.
    """

    flow = models.ForeignKey(
        FlowDefinition,
        related_name="steps",
        on_delete=models.CASCADE,
        help_text="The flow this step belongs to.",
    )
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        related_name="children",
        on_delete=models.CASCADE,
        help_text="The parent step of this step.",
    )
    action = models.CharField(
        max_length=50,
        choices=FlowActionChoices.choices,
        help_text="The action this step performs.",
    )
    variable_name = models.CharField(
        max_length=255,
        blank=True,
        help_text=(
            "For conditions, the flow variable to evaluate; for service functions, the target name."
        ),
    )
    parameters = models.JSONField(
        blank=True,
        help_text="Additional parameters for this step.",
    )

    def _parameters_mapping(self) -> dict[str, Any]:
        """Return step parameters as a dictionary."""
        if isinstance(self.parameters, dict):
            return cast(dict[str, Any], self.parameters)
        return {}

    def execute(self, flow_execution):
        """Execute this step and return the next step."""
        if self.action in CONDITIONAL_ACTIONS:
            return self._handle_conditional(flow_execution)

        action_map = {
            FlowActionChoices.SET_CONTEXT_VALUE: self._execute_set_context_value,
            FlowActionChoices.MODIFY_CONTEXT_VALUE: (self._execute_modify_context_value),
            FlowActionChoices.ADD_CONTEXT_LIST_VALUE: (self._execute_add_context_list_value),
            FlowActionChoices.REMOVE_CONTEXT_LIST_VALUE: (self._execute_remove_context_list_value),
            FlowActionChoices.SET_CONTEXT_DICT_VALUE: (self._execute_set_context_dict_value),
            FlowActionChoices.REMOVE_CONTEXT_DICT_VALUE: (self._execute_remove_context_dict_value),
            FlowActionChoices.MODIFY_CONTEXT_DICT_VALUE: (self._execute_modify_context_dict_value),
            FlowActionChoices.CALL_SERVICE_FUNCTION: (self._execute_call_service_function),
            FlowActionChoices.EMIT_FLOW_EVENT: self._execute_emit_flow_event,
            FlowActionChoices.EMIT_FLOW_EVENT_FOR_EACH: (self._execute_emit_flow_event_for_each),
        }
        handler = action_map.get(self.action)
        if handler:
            return handler(flow_execution)
        return flow_execution.get_next_child(self)

    def _handle_conditional(self, flow_execution):
        condition_passed = self._execute_conditional(flow_execution)
        if condition_passed:
            return flow_execution.get_next_child(self)
        return flow_execution.get_next_sibling(self)

    def _execute_conditional(self, flow_execution: "FlowExecution") -> bool:
        """Compare a flow variable to ``parameters['value']`` and return a boolean."""

        left_value = flow_execution.get_variable(str(self.variable_name))
        op_func = OPERATOR_MAP[self.action]
        params = self._parameters_mapping()
        comp_raw = params.get("value")
        try:
            # Handle special case where left_value type doesn't accept arguments
            left_type = type(left_value)
            if left_type in (object, type(None), type):
                right_value = comp_raw  # Can't convert these types with args
            else:
                right_value = left_type(comp_raw)
        except (TypeError, ValueError):
            # Fallback if type conversion fails
            right_value = comp_raw

        # Cast for mypy - we know these support comparison from OPERATOR_MAP
        return bool(op_func(cast(Any, left_value), cast(Any, right_value)))

    def _execute_set_context_value(
        self,
        flow_execution: "FlowExecution",
    ) -> Optional["FlowStepDefinition"]:
        """Set a value in the flow execution context."""
        object_pk = flow_execution.get_variable(str(self.variable_name))
        if object_pk is None:
            msg = f"Flow variable '{self.variable_name}' is undefined – cannot set context value."
            raise RuntimeError(
                msg,
            )
        params = self._parameters_mapping()
        attribute_name = params.get("attribute")
        literal_value = params.get("value")
        if attribute_name is None:
            msg = "Flow parameters missing 'attribute' for set context value."
            raise RuntimeError(msg)
        flow_execution.context.set_context_value(
            key=object_pk,
            attribute=attribute_name,
            value=literal_value,
        )
        return flow_execution.get_next_child(self)

    def _execute_modify_context_value(self, flow_execution):
        """Modify a value in the flow execution context using a modifier."""
        object_pk = flow_execution.get_variable(str(self.variable_name))
        if object_pk is None:
            msg = (
                f"Flow variable '{self.variable_name}' is undefined - cannot modify context value."
            )
            raise RuntimeError(
                (msg),
            )
        params = self._parameters_mapping()
        attribute_name = params.get("attribute")
        if attribute_name is None:
            msg = "Flow parameters missing 'attribute' for modify context value."
            raise RuntimeError(msg)
        modifier_spec = params.get("modifier")
        if modifier_spec is None:
            msg = "Flow parameters missing 'modifier' for modify context value."
            raise RuntimeError(msg)
        modifier_callable = resolve_modifier(
            flow_execution,
            modifier_spec,
        )
        flow_execution.context.modify_context_value(
            key=object_pk,
            attribute=attribute_name,
            modifier=modifier_callable,
        )
        return flow_execution.get_next_child(self)

    def _execute_add_context_list_value(self, flow_execution):
        """Append a value to a list stored on a state."""

        object_pk = flow_execution.get_variable(str(self.variable_name))
        if object_pk is None:
            msg = f"Flow variable '{self.variable_name}' is undefined - cannot add list value."
            raise RuntimeError(
                msg,
            )
        params = self._parameters_mapping()
        attribute_name = params.get("attribute")
        if attribute_name is None:
            msg = "Flow parameters missing 'attribute' for add list value."
            raise RuntimeError(msg)
        value_ref = params.get("value")
        value = flow_execution.resolve_flow_reference(value_ref)
        flow_execution.context.add_to_context_list(
            key=object_pk,
            attribute=attribute_name,
            value=value,
        )
        return flow_execution.get_next_child(self)

    def _execute_remove_context_list_value(self, flow_execution):
        """Remove a value from a list stored on a state."""

        object_pk = flow_execution.get_variable(str(self.variable_name))
        if object_pk is None:
            msg = f"Flow variable '{self.variable_name}' is undefined - cannot remove list value."
            raise RuntimeError(
                msg,
            )
        params = self._parameters_mapping()
        attribute_name = params.get("attribute")
        if attribute_name is None:
            msg = "Flow parameters missing 'attribute' for remove list value."
            raise RuntimeError(msg)
        value_ref = params.get("value")
        value = flow_execution.resolve_flow_reference(value_ref)
        flow_execution.context.remove_from_context_list(
            key=object_pk,
            attribute=attribute_name,
            value=value,
        )
        return flow_execution.get_next_child(self)

    def _execute_set_context_dict_value(self, flow_execution):
        """Set a key/value pair on a dict stored on a state."""

        object_pk = flow_execution.get_variable(str(self.variable_name))
        if object_pk is None:
            msg = f"Flow variable '{self.variable_name}' is undefined - cannot set dict value."
            raise RuntimeError(
                msg,
            )
        params = self._parameters_mapping()
        attribute_name = params.get("attribute")
        if attribute_name is None:
            msg = "Flow parameters missing 'attribute' for set dict value."
            raise RuntimeError(msg)
        dict_key_ref = params.get("key")
        dict_key = flow_execution.resolve_flow_reference(dict_key_ref)
        value_ref = params.get("value")
        value = flow_execution.resolve_flow_reference(value_ref)
        flow_execution.context.set_context_dict_value(
            key=object_pk,
            attribute=attribute_name,
            dict_key=dict_key,
            value=value,
        )
        return flow_execution.get_next_child(self)

    def _execute_remove_context_dict_value(self, flow_execution):
        """Remove a key from a dict stored on a state."""

        object_pk = flow_execution.get_variable(str(self.variable_name))
        if object_pk is None:
            msg = f"Flow variable '{self.variable_name}' is undefined - cannot remove dict value."
            raise RuntimeError(
                msg,
            )
        params = self._parameters_mapping()
        attribute_name = params.get("attribute")
        if attribute_name is None:
            msg = "Flow parameters missing 'attribute' for remove dict value."
            raise RuntimeError(msg)
        dict_key_ref = params.get("key")
        dict_key = flow_execution.resolve_flow_reference(dict_key_ref)
        flow_execution.context.remove_context_dict_value(
            key=object_pk,
            attribute=attribute_name,
            dict_key=dict_key,
        )
        return flow_execution.get_next_child(self)

    def _execute_modify_context_dict_value(self, flow_execution):
        """Modify a value stored in a dict attribute using a modifier."""

        object_pk = flow_execution.get_variable(self.variable_name)
        if object_pk is None:
            msg = f"Flow variable '{self.variable_name}' is undefined - cannot modify dict value."
            raise RuntimeError(
                msg,
            )
        params = self._parameters_mapping()
        attribute_name = params.get("attribute")
        if attribute_name is None:
            msg = "Flow parameters missing 'attribute' for modify dict value."
            raise RuntimeError(msg)
        dict_key_ref = params.get("key")
        dict_key = flow_execution.resolve_flow_reference(dict_key_ref)
        modifier_spec = params.get("modifier")
        if modifier_spec is None:
            msg = "Flow parameters missing 'modifier' for modify dict value."
            raise RuntimeError(msg)
        modifier_callable = resolve_modifier(
            flow_execution,
            modifier_spec,
        )
        flow_execution.context.modify_context_dict_value(
            key=object_pk,
            attribute=attribute_name,
            dict_key=dict_key,
            modifier=modifier_callable,
        )
        return flow_execution.get_next_child(self)

    def resolve_modifier(self, flow_execution):
        """Return a callable modifier resolved from step parameters."""
        params = self._parameters_mapping()
        modifier_spec = params.get("modifier")
        if modifier_spec is None:
            msg = "Flow parameters missing 'modifier' for modifier resolution."
            raise RuntimeError(msg)
        return resolve_modifier(flow_execution, modifier_spec)

    def _execute_call_service_function(self, flow_execution):
        """Invoke a service function and optionally store its result."""
        service_function = flow_execution.get_service_function(self.variable_name)
        params = {
            key: (flow_execution.resolve_flow_reference(val) if key != "result_variable" else val)
            for key, val in self._parameters_mapping().items()
        }
        result = service_function(flow_execution, **params)
        result_var = params.get("result_variable")
        if result_var:
            flow_execution.set_variable(result_var, result)
        return flow_execution.get_next_child(self)

    def _execute_emit_flow_event(self, flow_execution):
        """Create and dispatch a :class:`FlowEvent`."""
        params = self._parameters_mapping()
        event_type = params.get("event_type", self.variable_name)
        event_data = params.get("data", {})
        resolved_data = {
            key: flow_execution.resolve_flow_reference(value) for key, value in event_data.items()
        }
        flow_event = FlowEvent(event_type, source=flow_execution, data=resolved_data)
        flow_execution.context.store_flow_event(self.variable_name, flow_event)
        trigger_registry = flow_execution.get_trigger_registry()
        trigger_registry.process_event(
            flow_event,
            flow_execution.flow_stack,
            flow_execution.context,
        )
        if flow_event.stop_propagation:
            return None
        return flow_execution.get_next_child(self)

    def _execute_emit_flow_event_for_each(self, flow_execution):
        """Emit an event for every item in an iterable."""

        params = self._parameters_mapping()
        iterable_ref = params.get("iterable")
        if iterable_ref is None:
            return flow_execution.get_next_child(self)

        iterable = flow_execution.resolve_flow_reference(iterable_ref)
        event_type = params.get("event_type", self.variable_name)
        base_data = params.get("data", {})
        item_key = params.get("item_key", "item")
        next_step = flow_execution.get_next_child(self)
        for idx, item in enumerate(iterable or []):
            data = {
                key: (item if val == "@item" else flow_execution.resolve_flow_reference(val))
                for key, val in base_data.items()
            }
            if item_key:
                data.setdefault(item_key, item)
            flow_event = FlowEvent(event_type, source=flow_execution, data=data)
            context_key = f"{self.variable_name}_{idx}"
            flow_execution.context.store_flow_event(context_key, flow_event)
            trigger_registry = flow_execution.get_trigger_registry()
            trigger_registry.process_event(
                flow_event,
                flow_execution.flow_stack,
                flow_execution.context,
            )
            if flow_event.stop_propagation:
                return None
        return next_step

    def __str__(self) -> str:
        return f"{self.flow.name} - Step: {self.pk} ({self.action})"
