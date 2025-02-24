from django.db import models

from flows.consts import OPERATOR_MAP, FlowActionChoices


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

        For conditional steps, retrieves the value of the flow variable specified by
        'variable_name', casts the 'value' in parameters to that type, and compares
        using the operator determined by the action. If the condition fails, it returns
        the next sibling step; otherwise, it returns the first child step.

        For SET_CONTEXT_VALUE or MODIFY_CONTEXT_VALUE, it sets or modifies the global
        context.

        For CALL_SERVICE_FUNCTION, it looks up and calls the service function with the
        parameters, and if 'result_variable' is provided in parameters, stores the
        result in the flow variables.

        Returns the next FlowStepDefinition to execute (determined via flow_execution's
        helpers), or None if the flow is complete.
        """
        # Get shared context and flow variable mapping.
        # Note: flow_execution provides methods like get_variable, set_variable,
        # get_next_child, and get_next_sibling.
        if self.action in (
            FlowActionChoices.EVALUATE_EQUALS,
            FlowActionChoices.EVALUATE_NOT_EQUALS,
            FlowActionChoices.EVALUATE_LESS_THAN,
            FlowActionChoices.EVALUATE_GREATER_THAN,
            FlowActionChoices.EVALUATE_GREATER_THAN_OR_EQUALS,
            FlowActionChoices.EVALUATE_LESS_THAN_OR_EQUALS,
        ):
            # Conditional step.
            left_value = flow_execution.get_variable(self.variable_name)
            op_func = OPERATOR_MAP[self.action]
            # Get the 'value' from parameters and cast it to the type of left_value.
            comp_raw = self.parameters.get("value")
            # Let it blow up on TypeError if conversion fails.
            right_value = type(left_value)(comp_raw)
            if not op_func(left_value, right_value):
                return flow_execution.get_next_sibling(self)
            else:
                return flow_execution.get_next_child(self)
        elif self.action == FlowActionChoices.SET_CONTEXT_VALUE:
            # Here, variable_name is interpreted as the key for a context value.
            value_to_set = self.parameters.get("value")
            flow_execution.context.set_context_value(self.variable_name, value_to_set)
            return flow_execution.get_next_child(self)
        elif self.action == FlowActionChoices.MODIFY_CONTEXT_VALUE:
            # Similar to SET_CONTEXT_VALUE, but may involve modification logic.
            value_to_modify = self.parameters.get("value")
            flow_execution.context.modify_context_value(
                self.variable_name, value_to_modify
            )
            return flow_execution.get_next_child(self)
        elif self.action == FlowActionChoices.CALL_SERVICE_FUNCTION:
            # Look up the service function from an explicit mapping.
            service_function = flow_execution.get_service_function(self.variable_name)
            result = service_function(flow_execution, **self.parameters)
            # If parameters include a "result_variable", store the result in the flow's
            # variable mapping.
            result_var = self.parameters.get("result_variable")
            if result_var:
                flow_execution.set_variable(result_var, result)
            return flow_execution.get_next_child(self)
        else:
            # Default: simply proceed to the next child.
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
