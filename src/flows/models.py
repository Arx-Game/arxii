from django.db import models

from flows.consts import FlowActionChoices


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
    target_field = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="The key in the context or flow data to operate on.",
    )
    target_value = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="The value to compare against (for conditions) or set (for actions).",
    )
    description = models.TextField(
        blank=True, null=True, help_text="Optional description for this step."
    )

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
