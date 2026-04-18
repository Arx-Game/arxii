"""Unified event emission for the reactive layer.

Dispatches ``event_name`` to every ``trigger_handler`` reachable from
``location``: the location itself and every object in its ``contents``.
Triggers from every owner are gathered into one list, sorted globally
by priority descending, and walked synchronously on a single FlowStack.
Cancellation stops the walk.
"""

import logging
from typing import Any

from flows.filters.errors import FilterPathError
from flows.filters.evaluator import evaluate_filter
from flows.flow_stack import FlowStack

logger = logging.getLogger(__name__)


def emit_event(
    event_name: str,
    payload: Any,
    location: Any = None,
    *,
    parent_stack: FlowStack | None = None,
    **_legacy_kwargs: Any,
) -> FlowStack:
    """Dispatch ``event_name`` to every handler in ``location`` + contents.

    Args:
        event_name: The event name, e.g. ``EventNames.DAMAGE_PRE_APPLY``.
        payload: A payload dataclass from ``flows.events.payloads``.
        location: The location whose ``trigger_handler`` and whose
            ``contents``' handlers are consulted.
        parent_stack: When supplied (nested emission from within a
            running flow) the same FlowStack is reused so the recursion
            cap is enforced on the originating chain.

    Returns:
        The FlowStack used for the dispatch. Callers check
        ``stack.was_cancelled()`` to decide whether to suppress the
        default behaviour (skip damage apply, abort movement, etc.).

    ``**_legacy_kwargs`` transitionally swallows the old
    ``personal_target=`` / ``room=`` kwargs still used by unrewritten
    callsites. Phase 3 removes those callsites; this shim goes with them.
    """
    stack = parent_stack or FlowStack(owner=location, originating_event=event_name)

    owners: list[Any] = [location]
    contents = getattr(location, "contents", None) or []  # noqa: GETATTR_LITERAL
    owners.extend(contents)

    gathered: list[Any] = []
    for owner in owners:
        handler = getattr(owner, "trigger_handler", None)  # noqa: GETATTR_LITERAL
        if handler is None:
            continue
        gathered.extend(handler.triggers_for(event_name))

    gathered.sort(key=lambda t: -t.priority)

    for trigger in gathered:
        try:
            matched = evaluate_filter(
                trigger.additional_filter_condition,
                payload,
                self_ref=trigger.obj,
            )
        except FilterPathError:
            logger.warning(
                "FilterPathError on trigger %s during dispatch of %s",
                trigger.pk,
                event_name,
            )
            continue
        if not matched:
            continue
        _execute_flow(trigger, payload, stack)
        if stack.was_cancelled():
            break

    return stack


def _execute_flow(trigger: Any, payload: Any, stack: FlowStack) -> None:
    """Execute ``trigger``'s flow definition on ``stack``."""
    from flows.flow_execution import FlowExecution  # noqa: PLC0415 — Evennia startup
    from flows.scene_data_manager import SceneDataManager  # noqa: PLC0415 — same reason
    from flows.trigger_handler import DispatchResult  # noqa: PLC0415 — same reason

    flow_def = trigger.trigger_definition.flow_definition
    context = SceneDataManager()
    execution = FlowExecution(
        flow_definition=flow_def,
        context=context,
        flow_stack=stack,
        origin=trigger,
        variable_mapping={
            "payload": payload,
            "owner": trigger.obj,
            "trigger": trigger,
        },
        dispatch_result=DispatchResult(),
    )
    stack.execute_flow(execution)
