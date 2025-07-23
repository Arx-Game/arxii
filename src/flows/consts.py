from enum import Enum, auto
import operator

from django.db import models


class NotificationTiming(models.TextChoices):
    PRE_PROCESS = "PRE_PROCESS", "Pre-processing"
    POST_PROCESS = "POST_PROCESS", "Post-processing"


class EventType(models.TextChoices):
    EXAMINE = "EXAMINE", "Examine"
    ATTACK = "ATTACK", "Attack"
    MOVE = "MOVE", "Move"
    TALK = "TALK", "Talk"
    USE = "USE", "Use"
    MAGIC = "MAGIC", "Magic"
    KILL = "KILL", "Kill"
    DAMAGE = "DAMAGE", "Damage"
    # Add more event types as needed


class FlowActionChoices(models.TextChoices):
    """
    Choices for actions that can be performed by a flow step.
    """

    SET_CONTEXT_VALUE = "set_context_value", "Set Context Value"
    MODIFY_CONTEXT_VALUE = "modify_context_value", "Modify Context Value"
    EVALUATE_EQUALS = "evaluate_equals", "Evaluate Equals"
    EVALUATE_NOT_EQUALS = "evaluate_not_equals", "Evaluate Not Equals"
    EVALUATE_LESS_THAN = "evaluate_less_than", "Evaluate Less Than"
    EVALUATE_GREATER_THAN = "evaluate_greater_than", "Evaluate Greater Than"
    EVALUATE_LESS_THAN_OR_EQUALS = (
        "evaluate_less_than_or_equals",
        "Evaluate Less Than or Equals",
    )
    EVALUATE_GREATER_THAN_OR_EQUALS = (
        "evaluate_greater_than_or_equals",
        "Evaluate Greater Than or Equals",
    )
    CALL_SERVICE_FUNCTION = "call_service_function", "Call Service Function"
    EMIT_FLOW_EVENT = "emit_flow_event", "Emit Flow Event"
    EMIT_FLOW_EVENT_FOR_EACH = (
        "emit_flow_event_for_each",
        "Emit Flow Event For Each",
    )


# Map the comparison actions to their corresponding operator functions.
# (Only the evaluate_* actions need mapping.)
OPERATOR_MAP = {
    FlowActionChoices.EVALUATE_EQUALS: operator.eq,
    FlowActionChoices.EVALUATE_NOT_EQUALS: operator.ne,
    FlowActionChoices.EVALUATE_LESS_THAN: operator.lt,
    FlowActionChoices.EVALUATE_GREATER_THAN: operator.gt,
    FlowActionChoices.EVALUATE_LESS_THAN_OR_EQUALS: operator.le,
    FlowActionChoices.EVALUATE_GREATER_THAN_OR_EQUALS: operator.ge,
}


class FlowState(Enum):
    """Simple execution state used by handlers."""

    RUNNING = auto()
    STOP = auto()


class DefaultEvents(models.TextChoices):
    """
    Default event types that can be listened for or emitted.
    """

    ATTACK = "attack", "Attack"
    EXAMINE = "examine", "Examine"
    MOVE = "move", "Move"


PRE_FLIGHT_FLOW_NAME = "preflight"
