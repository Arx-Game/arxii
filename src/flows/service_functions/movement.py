"""Movement-related service functions."""

from commands.exceptions import CommandError
from flows.flow_execution import FlowExecution


def move_object(
    flow_execution: FlowExecution,
    obj: str,
    destination: str,
    quiet: bool = True,
    **kwargs: object,
) -> None:
    """Move an object to ``destination``.

    Args:
        flow_execution: Current execution context.
        obj: Name of the flow variable referencing the object to move.
        destination: Name of the flow variable referencing the destination.
        quiet: Passed to ``move_to`` to suppress hooks and messages.
        **kwargs: Additional keyword arguments for ``move_to``.

    Raises:
        CommandError: If the move cannot be completed.

    Example:
        ````python
        FlowStepDefinition(
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
            variable_name="move_object",
            parameters={"obj": "$item", "destination": "$room"},
        )
        ````
    """

    obj_state = flow_execution.get_object_state(obj)
    dest_state = flow_execution.get_object_state(destination)

    if obj_state is None or dest_state is None:
        raise CommandError("Invalid object or destination.")

    if not obj_state.can_move(obj_state, dest_state):
        raise CommandError("Move not permitted.")

    success = obj_state.obj.move_to(dest_state.obj, quiet=quiet, **kwargs)

    if not success:
        raise CommandError("Could not move object.")
