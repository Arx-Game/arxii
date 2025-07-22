# Flow Examples

This document showcases how data-driven flows allow designers to create complex behaviors with no hardcoded game logic.

## Evil Name Example

The test suite demonstrates a flow that marks characters as evil based on a tag. A room flow emits a `glance` event for each occupant. A second flow listens for that event and appends "(Evil)" to the character name if the target has an `evil` tag.

1. **Iterate room contents**
   ```python
   FlowStepDefinition(
       action=FlowActionChoices.EMIT_FLOW_EVENT_FOR_EACH,
       variable_name="glance",
       parameters={"iterable": "$room.contents", "event_type": "glance", "data": {"target": "$item"}},
   )
   ```
2. **Check for the tag and modify the name**
   ```python
   FlowStepDefinition(
       action=FlowActionChoices.CALL_SERVICE_FUNCTION,
       variable_name="object_has_tag",
       parameters={"obj": "$event.data.target", "tag": "evil", "result_variable": "is_evil"},
   )
   FlowStepDefinition(
       action=FlowActionChoices.EVALUATE_EQUALS,
       variable_name="is_evil",
       parameters={"value": "True"},
   )
   FlowStepDefinition(
       action=FlowActionChoices.CALL_SERVICE_FUNCTION,
       variable_name="append_to_attribute",
       parameters={"obj": "$event.data.target", "attribute": "name", "append_text": " (Evil)"},
   )
   ```

When executed, any character with the `evil` tag has "(Evil)" appended to their name, demonstrating how flows, triggers and service functions work together to implement dynamic behavior.

## Trigger Registry Integration

Rooms maintain a ``TriggerRegistry`` that tracks active triggers. Pass this
registry to ``FlowStack`` when creating one for a room. Every ``FlowEvent``
emitted by a flow is forwarded to the registry so triggers can spawn new flows.
If ``event.stop_propagation`` becomes ``True`` the registry stops further
processing.

## Filtering Triggers with Event Data

Triggers can limit when they fire using ``base_filter_condition``. The
``EMIT_FLOW_EVENT`` step resolves variable references so event data can contain
object identifiers. For example:

```python
FlowStepDefinition(
    action=FlowActionChoices.EMIT_FLOW_EVENT,
    variable_name="glance",
    parameters={
        "event_type": "glance",
        "data": {"caller": "$caller.pk", "target": "$target.pk"},
    },
)
```

A trigger definition can filter on those values:

```python
TriggerDefinition(
    event=Event.objects.get(key="glance"),
    flow_definition=response_flow,
    base_filter_condition={"caller": 1, "target": 2},
)
```

When a ``glance`` event is emitted with matching ``caller`` and ``target``
identifiers, the trigger activates and spawns ``response_flow``.

Trigger conditions may also use ``$self`` to refer to the object the trigger is
on. This allows a single ``TriggerDefinition`` to be reused by many objects:

```python
TriggerDefinition(
    event=Event.objects.get(key="glance"),
    flow_definition=response_flow,
    base_filter_condition={"target": "$self"},
)
```

Each trigger based on this definition will fire only when the event's
``target`` matches the object hosting the trigger.
