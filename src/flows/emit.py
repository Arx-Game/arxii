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
    location: Any,
    *,
    parent_stack: FlowStack | None = None,
) -> FlowStack:
    """Dispatch ``event_name`` to every handler in ``location`` + contents.

    Args:
        event_name: The event name, e.g. ``EventName.DAMAGE_PRE_APPLY``.
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
    """
    stack = parent_stack or FlowStack(owner=location, originating_event=event_name)

    gathered = _gather_triggers(event_name, location)
    gathered.sort(key=lambda t: -t.priority)

    for trigger in gathered:
        if not _trigger_should_fire(trigger, payload, event_name):
            continue
        _execute_flow(trigger, payload, stack)
        handler = getattr(trigger.obj, "trigger_handler", None)  # noqa: GETATTR_LITERAL
        if handler is not None:
            handler.note_fired(trigger.pk)
        if stack.was_cancelled():
            break

    return stack


def _gather_triggers(event_name: str, location: Any) -> list[Any]:
    """Collect every trigger for ``event_name`` from ``location`` + its contents."""
    owners: list[Any] = [location]
    contents = getattr(location, "contents", None) or []  # noqa: GETATTR_LITERAL
    owners.extend(contents)

    gathered: list[Any] = []
    for owner in owners:
        handler = getattr(owner, "trigger_handler", None)  # noqa: GETATTR_LITERAL
        if handler is None:
            continue
        gathered.extend(handler.triggers_for(event_name))
    return gathered


def _trigger_should_fire(trigger: Any, payload: Any, event_name: str) -> bool:
    """Whether ``trigger`` passes its filter and is under its dispatch usage cap."""
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
        return False
    if not matched:
        return False

    handler = getattr(trigger.obj, "trigger_handler", None)  # noqa: GETATTR_LITERAL
    limit = _dispatch_usage_limit(trigger, event_name)
    if handler is not None and limit is not None and handler.fire_count(trigger.pk) >= limit:
        return False
    return True


def _dispatch_usage_limit(trigger: Any, event_name: str) -> int | None:
    """Cap for dispatch purposes. ``None`` = unlimited.

    Only an EXPLICITLY-authored usage_limit key caps dispatch; absence means
    unlimited.  ``get_usage_limit``'s default-of-1 is event-semantics, not a
    cross-emit dispatch cap — we must NOT apply it here to avoid suppressing
    triggers that lack any usage_limit key after the first emit.

    Args:
        trigger: A ``Trigger`` model instance.
        event_name: The event name currently being dispatched.

    Returns:
        ``None`` if no explicit cap is authored; otherwise the positive integer
        cap (values ``<= 0`` are already mapped to ``None`` by
        ``get_usage_limit``).
    """
    data_map = trigger.data_map
    # "usage_limit" is a TriggerData key name — a database identifier, not a code constant.
    if f"usage_limit_{event_name}" not in data_map and "usage_limit" not in data_map:  # noqa: STRING_LITERAL
        return None
    return trigger.get_usage_limit(event_name)


def _execute_flow(trigger: Any, payload: Any, stack: FlowStack) -> None:
    """Execute ``trigger``'s flow definition on ``stack``."""
    from flows.flow_execution import FlowExecution  # noqa: PLC0415
    from flows.scene_data_manager import SceneDataManager  # noqa: PLC0415
    from flows.trigger_handler import DispatchResult  # noqa: PLC0415

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
