from typing import List

from django.db import models
from django.utils.functional import cached_property

from flows.flow_event import FlowEvent
from flows.helpers.logic import resolve_self_placeholders
from flows.models.events import Event
from flows.models.flows import FlowDefinition


class TriggerDefinition(models.Model):
    """Reusable template describing when to launch another flow.

    ``base_filter_condition`` allows simple equality checks against event data to
    decide if the trigger should fire. For example, given a ``glance`` event::

        TriggerDefinition(
            name="on glance at me",
            event=Event.objects.get(key="glance"),
            flow_definition=response_flow,
            base_filter_condition={"target": 5},
        )

    A trigger based on this definition will only activate when the ``glance``
    event's ``target`` equals ``5`` (the object's primary key).
    """

    name = models.CharField(max_length=255, unique=True)
    event = models.ForeignKey(
        Event,
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
        blank=True,
        null=True,
        help_text="Optional description of the trigger.",
    )
    priority = models.IntegerField(
        default=0,
        help_text="Higher priority triggers fire first.",
    )

    def matches_event(self, event: FlowEvent, obj=None) -> bool:
        conditions = resolve_self_placeholders(self.base_filter_condition, obj)
        return self.event.key == event.event_type and event.matches_conditions(
            conditions
        )

    def __str__(self) -> str:
        return self.name


class Trigger(models.Model):
    """Represents an active trigger on an object, based on a TriggerDefinition."""

    trigger_definition = models.ForeignKey(
        TriggerDefinition,
        on_delete=models.CASCADE,
        help_text="The trigger template this is based on.",
    )
    obj = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.CASCADE,
        related_name="triggers",
        help_text="The object this trigger is associated with.",
    )
    additional_filter_condition = models.JSONField(
        blank=True,
        null=True,
        help_text="Optional JSON condition to further refine when this trigger activates.",
    )

    @cached_property
    def trigger_data_items(self) -> List["TriggerData"]:
        return list(self.data.all())

    @property
    def data_map(self) -> dict[str, str]:
        return {d.key: d.value for d in self.trigger_data_items}

    @property
    def priority(self) -> int:
        return self.trigger_definition.priority

    def should_trigger_for_event(self, event: FlowEvent) -> bool:
        if not self.trigger_definition.matches_event(event, obj=self.obj):
            return False
        additional = resolve_self_placeholders(
            self.additional_filter_condition, self.obj
        )
        return event.matches_conditions(additional)

    def __str__(self) -> str:
        return f"{self.trigger_definition.name} for {self.obj.key}"


class TriggerData(models.Model):
    """Stores long-lived, arbitrary data associated with a specific Trigger."""

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

    def __str__(self) -> str:
        return f"Data for {self.trigger} - {self.key}: {self.value}"
