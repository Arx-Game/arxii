"""Read-only cross-reference builder for the flow retrieve endpoint (#3417 task 5).

A flow doesn't only run when a caller directly invokes it — a
``TriggerDefinition`` can be set to run it in response to an event, the flow's
own steps can emit events other triggers listen for, and its steps can call
service functions. None of these relationships are visible on the flow row
itself, so this module batches them into a single ``interactions`` dict for
the authoring UI: "what runs this flow, what does it emit and who's listening,
what does it call."

Query discipline: ``run_by`` is one query (``prefetch_related`` handles
``installing_templates`` per-row without N+1); ``emits`` listeners are one
``event_name__in`` query grouped in Python; steps are never re-queried here —
callers pass the already-prefetched step list (or, for a direct caller with
no prefetch, ``flow.steps.all()`` supplies it once).
"""

from collections import defaultdict
from typing import Any

from django.db.models import Prefetch

from flows.consts import FlowActionChoices
from flows.models import FlowDefinition, FlowStepDefinition, TriggerDefinition

_EMIT_ACTIONS = frozenset(
    {
        FlowActionChoices.EMIT_FLOW_EVENT,
        FlowActionChoices.EMIT_FLOW_EVENT_FOR_EACH,
    }
)


def flow_interactions(flow: FlowDefinition) -> dict[str, Any]:
    """Build the ``run_by`` / ``emits`` / ``calls`` cross-reference for ``flow``.

    ``flow`` should carry ``prefetched_steps`` (the viewset's retrieve-time
    ``Prefetch(..., to_attr="prefetched_steps")``) when available; otherwise
    this falls back to ``flow.steps.all()`` for a direct (non-viewset) caller.
    """
    try:
        steps = flow.prefetched_steps
    except AttributeError:
        steps = list(flow.steps.all())

    return {
        "run_by": _run_by(flow),
        "emits": _emits(steps),
        "calls": _calls(steps),
    }


def _run_by(flow: FlowDefinition) -> list[dict[str, Any]]:
    triggers = TriggerDefinition.objects.filter(flow_definition=flow).prefetch_related(
        Prefetch("installing_templates", to_attr="prefetched_installing_templates")
    )
    return [
        {
            "id": trigger.pk,
            "name": trigger.name,
            "event_name": trigger.event_name,
            "installing_templates": [
                {"id": template.pk, "name": template.name}
                for template in trigger.prefetched_installing_templates
            ],
        }
        for trigger in triggers
    ]


def _emits(steps: list[FlowStepDefinition]) -> list[dict[str, Any]]:
    event_names: list[str] = []
    for step in steps:
        if step.action not in _EMIT_ACTIONS:
            continue
        event_name = step.parameters.get("event_type") or step.variable_name
        if event_name and event_name not in event_names:
            event_names.append(event_name)

    listeners_by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trigger in TriggerDefinition.objects.filter(event_name__in=event_names):
        listeners_by_event[trigger.event_name].append({"id": trigger.pk, "name": trigger.name})

    return [
        {"event_name": event_name, "listeners": listeners_by_event.get(event_name, [])}
        for event_name in event_names
    ]


def _calls(steps: list[FlowStepDefinition]) -> list[str]:
    calls: list[str] = []
    for step in steps:
        if step.action != FlowActionChoices.CALL_SERVICE_FUNCTION:
            continue
        name = step.variable_name
        if name and name not in calls:
            calls.append(name)
    return calls
