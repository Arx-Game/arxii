from functools import cached_property

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from flows.flow_event import FlowEvent
from flows.helpers.logic import resolve_self_placeholders
from flows.models.events import Event
from flows.models.flows import FlowDefinition


class TriggerDefinition(SharedMemoryModel):
    """Reusable template describing when to launch another flow.

    ``base_filter_condition`` allows simple equality checks against event data to
    decide if the trigger should fire. For example, given a ``glance`` event::

        TriggerDefinition(
            name="on glance at me",
            event=Event.objects.get(name="glance"),
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

    def matches_event(self, event: FlowEvent, obj: object = None) -> bool:
        conditions = resolve_self_placeholders(self.base_filter_condition, obj)
        return self.event.name == event.event_type and event.matches_conditions(
            conditions,
        )

    def __str__(self) -> str:
        return str(self.name)


class Trigger(SharedMemoryModel):
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
        help_text=("Optional JSON condition to further refine when this trigger activates."),
    )

    @cached_property
    def trigger_data_items(self) -> list["TriggerData"]:
        return list(self.data.all())

    @property
    def data_map(self) -> dict[str, str]:
        return {d.key: d.value for d in self.trigger_data_items}

    @property
    def priority(self) -> int:
        return int(self.trigger_definition.priority)

    def get_usage_limit(self, event_type: str) -> int | None:
        """Return how many times this trigger may fire for ``event_type``.

        The limit is looked up in ``data_map`` using the key
        ``f"usage_limit_{event_type}"`` if present. If absent, ``usage_limit``
        is used as a generic fallback. If neither key is found, ``1`` is
        returned by default. Values less than or equal to ``0`` or ``None``
        disable the limit and ``None`` is returned.

        Args:
            event_type: The type of event currently being processed.

        Returns:
            Optional integer usage limit. ``None`` means unlimited.
        """

        limit_key = f"usage_limit_{event_type}"
        raw_value = self.data_map.get(limit_key, self.data_map.get("usage_limit"))

        if raw_value is None:
            return 1

        try:
            limit = int(raw_value)
        except (ValueError, TypeError):
            return None

        if limit <= 0:
            return None
        return limit

    def should_trigger_for_event(self, event: FlowEvent) -> bool:
        if not self.trigger_definition.matches_event(event, obj=self.obj):
            return False
        additional = resolve_self_placeholders(
            self.additional_filter_condition,
            self.obj,
        )
        return event.matches_conditions(additional)

    def __str__(self) -> str:
        return f"{self.trigger_definition.name} for {self.obj.key}"


class TriggerData(SharedMemoryModel):
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
