import functools
import json
import operator

from django.db import models

from flows.consts import OPERATOR_MAP, FlowActionChoices
from flows.flow_event import FlowEvent

# A constant encapsulating all conditional actions.
CONDITIONAL_ACTIONS = {
    FlowActionChoices.EVALUATE_EQUALS,
    FlowActionChoices.EVALUATE_NOT_EQUALS,
    FlowActionChoices.EVALUATE_LESS_THAN,
    FlowActionChoices.EVALUATE_GREATER_THAN,
    FlowActionChoices.EVALUATE_LESS_THAN_OR_EQUALS,
    FlowActionChoices.EVALUATE_GREATER_THAN_OR_EQUALS,
}


class Event(models.Model):
    """
    Represents an event type that triggers can listen for or emit.
    """

    key = models.CharField(
        max_length=50, primary_key=True, help_text="Unique identifier for the event."
    )
    label = models.CharField(
        max_length=255, help_text="Human-readable label for the event."
    )

    def __str__(self):
        return self.label


class FlowDefinition(models.Model):
    """
    Represents a reusable definition for a flow, consisting of multiple steps.
    """

    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name


class FlowStepDefinition(models.Model):
    """
    Represents a single step in a flow definition.

    The 'variable_name' field serves as a generic reference. Its meaning depends on the
     action:
      - For conditional steps (evaluate_equals, etc.), it names the flow variable to
      test.
      - For SET_CONTEXT_VALUE, it indicates which context variable to set.
      - For CALL_SERVICE_FUNCTION, it names the service function (or could be used to
      look it up).

    The 'parameters' JSONField stores extra parameters for the step. For a condition,
    it might be:
      { "value": "10" }
    For a service function, it might be a mapping of keyword arguments, e.g.,
      { "modifier": "5", "result_variable": "attack_result" }
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
        help_text="The key whose meaning depends on the action: for condition steps, "
        "the flow variable to evaluate; for service functions, the name of "
        "the service function or target context variable.",
    )
    parameters = models.JSONField(
        blank=True,
        help_text="A JSON object with parameters. For conditions, should include a key "
        "'value' (the value to compare against). For service functions, it’s "
        "a mapping of kwargs (and optionally 'result_variable' to store the "
        "output).",
    )

    def execute(self, flow_execution):
        """
        Executes this step within the given FlowExecution context.

        - For conditional steps, retrieves the flow variable specified by 'variable_name',
          casts the 'value' in parameters to the type of that variable, and compares using
          the operator defined by the action. If the condition passes, returns the next child;
          otherwise, returns the next sibling.
        - For SET_CONTEXT_VALUE/MODIFY_CONTEXT_VALUE, updates context data.
        - For CALL_SERVICE_FUNCTION, calls the service function and stores any result.
        - For EMIT_FLOW_EVENT, creates and stores a FlowEvent in the context.

        Returns the next FlowStepDefinition to execute, or None if the flow is complete.
        """
        if self.action in CONDITIONAL_ACTIONS:
            condition_passed = self._execute_conditional(flow_execution)
            if condition_passed:
                return flow_execution.get_next_child(self)
            else:
                return flow_execution.get_next_sibling(self)
        elif self.action == FlowActionChoices.SET_CONTEXT_VALUE:
            return self._execute_set_context_value(flow_execution)
        elif self.action == FlowActionChoices.MODIFY_CONTEXT_VALUE:
            return self._execute_modify_context_value(flow_execution)
        elif self.action == FlowActionChoices.CALL_SERVICE_FUNCTION:
            return self._execute_call_service_function(flow_execution)
        elif self.action == FlowActionChoices.EMIT_FLOW_EVENT:
            return self._execute_emit_flow_event(flow_execution)
        else:
            return flow_execution.get_next_child(self)

    def _execute_conditional(self, flow_execution):
        """
        Executes a conditional step by comparing a flow variable with a provided value.
        Returns True if the condition passes, False otherwise.
        """
        left_value = flow_execution.get_variable(self.variable_name)
        op_func = OPERATOR_MAP[self.action]
        comp_raw = self.parameters.get("value")
        right_value = type(left_value)(comp_raw)
        return op_func(left_value, right_value)

    def _execute_set_context_value(self, flow_execution):
        """
        variable_name - the *flow variable* holding an object pk
        parameters    - {
                            "attribute": "<field in ObjectState>",
                            "value":     <any JSON-serialisable literal>
                        }
        """
        object_pk = flow_execution.get_variable(self.variable_name)
        if object_pk is None:
            raise RuntimeError(
                f"Flow variable '{self.variable_name}' is undefined – "
                "cannot set context value."
            )

        attribute_name = self.parameters["attribute"]
        literal_value = self.parameters["value"]

        flow_execution.context.set_context_value(
            key=object_pk,
            attribute=attribute_name,
            value=literal_value,
        )
        return flow_execution.get_next_child(self)

    def _execute_modify_context_value(self, flow_execution):
        """
        parameters - {
            "attribute": "<field>",
            "function":  "<service fn name>",
            "value":     "<JSON object of args for function>"
        }

        For safety, resolve `modifier` via a registry or helper instead
        of `eval`.
        """
        object_pk = flow_execution.get_variable(self.variable_name)
        if object_pk is None:
            raise RuntimeError(
                f"Flow variable '{self.variable_name}' is undefined – "
                "cannot modify context value."
            )

        attribute_name = self.parameters["attribute"]

        # resolve modifier makes a partial function based on name and value
        modifier_callable = self.resolve_modifier(flow_execution)

        flow_execution.context.modify_context_value(
            key=object_pk,
            attribute=attribute_name,
            modifier=modifier_callable,
        )
        return flow_execution.get_next_child(self)

    def resolve_modifier(self, flow_execution) -> callable:
        """
        Resolves a modifier into a callable function for context modification.

        The ONLY valid schema for the modifier is:

            {
                "name": <str>,         # REQUIRED: the operator name (e.g. "add", "mul")
                "args": <list>,        # OPTIONAL: positional arguments
                "kwargs": <dict>       # OPTIONAL: keyword arguments
            }

        - Any deviation from this schema (missing "name", extra keys, wrong types)
        raises ValueError.
        - Operator name must be one of: add, sub, mul, truediv, floordiv, mod, pow,
        neg, pos, abs, eq, ne, lt, le, gt, ge.
        - Arguments that are strings starting with "$" will be resolved from flow
        variables, supporting dot notation for attribute access (e.g., "$foo.bar").

        Args:
            flow_execution: The FlowExecution instance for resolving variables.

        Returns:
            Callable that can be used as a modifier.

        Example:
            modifier = {
                "name": "add",
                "args": [3]
            }
            # Will produce: lambda old_value: operator.add(old_value, 3)
        """

        OP_FUNCS = {
            "add": operator.add,
            "sub": operator.sub,
            "mul": operator.mul,
            "truediv": operator.truediv,
            "floordiv": operator.floordiv,
            "mod": operator.mod,
            "pow": operator.pow,
            "neg": operator.neg,
            "pos": operator.pos,
            "abs": operator.abs,
            "eq": operator.eq,
            "ne": operator.ne,
            "lt": operator.lt,
            "le": operator.le,
            "gt": operator.gt,
            "ge": operator.ge,
        }

        # Only accept a dict or a JSON string that parses to a dict
        mod_spec = self.parameters.get("modifier")
        if isinstance(mod_spec, str):
            try:
                data = json.loads(mod_spec)
            except Exception:
                raise ValueError("Modifier must be a JSON object string or dict.")
        elif isinstance(mod_spec, dict):
            data = mod_spec
        else:
            raise ValueError("Modifier must be a JSON object string or dict.")

        # Strict schema enforcement
        allowed_keys = {"name", "args", "kwargs"}
        if not isinstance(data, dict):
            raise ValueError("Modifier must be a dict.")
        if set(data.keys()) - allowed_keys:
            raise ValueError(
                f"Modifier contains unknown keys: {set(data.keys()) - allowed_keys}"
            )
        if "name" not in data or not isinstance(data["name"], str):
            raise ValueError("Modifier must have a 'name' key of type str.")
        if "args" in data and not isinstance(data["args"], list):
            raise ValueError("Modifier 'args' must be a list if present.")
        if "kwargs" in data and not isinstance(data["kwargs"], dict):
            raise ValueError("Modifier 'kwargs' must be a dict if present.")

        func_name = data["name"]
        if func_name not in OP_FUNCS:
            raise ValueError(f"Unknown modifier/operator: {func_name}")
        func = OP_FUNCS[func_name]

        args = data.get("args", [])
        kwargs = data.get("kwargs", {})

        resolved_args = [flow_execution.resolve_flow_reference(a) for a in args]
        resolved_kwargs = {
            k: flow_execution.resolve_flow_reference(v) for k, v in kwargs.items()
        }

        return functools.partial(func, *resolved_args, **resolved_kwargs)

    def _execute_call_service_function(self, flow_execution):
        """
        Executes a step that calls a service function.
        """
        service_function = flow_execution.get_service_function(self.variable_name)
        result = service_function(flow_execution, **self.parameters)
        result_var = self.parameters.get("result_variable")
        if result_var:
            flow_execution.set_variable(result_var, result)
        return flow_execution.get_next_child(self)

    def _execute_emit_flow_event(self, flow_execution):
        """
        Executes a step to emit a FlowEvent.
        Creates a FlowEvent with the specified event type (or defaults to variable_name),
        stores it in context, and returns the next child step unless the event stops
        propagation.
        """
        event_type = self.parameters.get("event_type", self.variable_name)
        event_data = self.parameters.get("data", {})
        flow_event = FlowEvent(event_type, source=flow_execution, data=event_data)
        flow_execution.context.store_flow_event(self.variable_name, flow_event)
        if flow_event.stop_propagation:
            return None
        return flow_execution.get_next_child(self)

    def __str__(self):
        return f"{self.flow.name} - Step: {self.id} ({self.action})"


class TriggerDefinition(models.Model):
    """
    Represents a reusable template for triggers.
    """

    name = models.CharField(max_length=255, unique=True)
    event = models.ForeignKey(
        "Event",
        on_delete=models.CASCADE,
        db_column="event_id",
        help_text="The event this trigger listens for.",
    )
    flow_definition = models.ForeignKey(
        FlowDefinition,
        on_delete=models.CASCADE,
        help_text="The flow to execute when this trigger activates.",
    )
    base_filter_condition = models.JSONField(
        blank=True,
        null=True,
        help_text="Base JSON condition to filter when this trigger is valid.",
    )
    description = models.TextField(
        blank=True, null=True, help_text="Optional description of the trigger."
    )
    priority = models.IntegerField(
        default=0,
        help_text="Higher priority triggers fire first.",
    )

    def __str__(self):
        return self.name


class Trigger(models.Model):
    """
    Represents an active trigger on an object, based on a TriggerDefinition.
    """

    trigger_definition = models.ForeignKey(
        TriggerDefinition,
        on_delete=models.CASCADE,
        help_text="The trigger template this is based on.",
    )
    obj = models.ForeignKey(
        "object.ObjectDB",
        on_delete=models.CASCADE,
        related_name="triggers",
        help_text="The object this trigger is associated with.",
    )
    additional_filter_condition = models.JSONField(
        blank=True,
        null=True,
        help_text="Optional JSON condition to further refine when this trigger activates.",
    )

    def __str__(self):
        return f"{self.trigger_definition.name} for {self.obj.key}"


class TriggerData(models.Model):
    """
    Stores long-lived, arbitrary data associated with a specific Trigger.
    """

    trigger = models.ForeignKey(
        Trigger,
        on_delete=models.CASCADE,
        related_name="data",
        help_text="The specific trigger instance this data is associated with.",
    )
    key = models.CharField(max_length=255, help_text="The data key.")
    value = models.TextField(help_text="The data value.")

    class Meta:
        unique_together = ("trigger", "key")

    def __str__(self):
        return f"Data for {self.trigger} - {self.key}: {self.value}"
