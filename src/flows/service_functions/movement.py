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
            parameters={"obj": "@item", "destination": "@room"},
        )
        ````
    """

    obj_state = flow_execution.get_object_state(obj)
    dest_state = flow_execution.get_object_state(destination)

    if obj_state is None or dest_state is None:
        msg = "Invalid object or destination."
        raise CommandError(msg)

    if not obj_state.can_move(obj_state, dest_state):
        msg = "Move not permitted."
        raise CommandError(msg)

    success = obj_state.obj.move_to(dest_state.obj, quiet=quiet, **kwargs)

    if not success:
        msg = "Could not move object."
        raise CommandError(msg)


def check_exit_traversal(
    flow_execution: FlowExecution,
    caller: str,
    exit: str,
    **kwargs: object,
) -> None:
    """Check if the caller can traverse the exit.

    Args:
        flow_execution: Current execution context.
        caller: Name of the flow variable referencing the character attempting
            traversal.
        exit: Name of the flow variable referencing the exit being traversed.
        **kwargs: Additional keyword arguments.

    Raises:
        CommandError: If traversal is not permitted.
    """
    caller_state = flow_execution.get_object_state(caller)
    exit_state = flow_execution.get_object_state(exit)

    if caller_state is None or exit_state is None:
        msg = "Invalid caller or exit."
        raise CommandError(msg)

    if not exit_state.can_traverse(caller_state):
        msg = "You cannot go that way."
        raise CommandError(msg)

    # Check if the exit has a destination
    if not hasattr(exit_state.obj, "destination") or not exit_state.obj.destination:
        msg = "That exit doesn't lead anywhere."
        raise CommandError(msg)


def traverse_exit(
    flow_execution: FlowExecution,
    caller: str,
    exit: str,
    destination: str,
    **kwargs: object,
) -> None:
    """Move the caller through the exit to its destination.

    Args:
        flow_execution: Current execution context.
        caller: Name of the flow variable referencing the character.
        exit: Name of the flow variable referencing the exit.
        destination: Name of the flow variable referencing the destination.
        **kwargs: Additional keyword arguments.

    Raises:
        CommandError: If the traversal cannot be completed.
    """
    caller_state = flow_execution.get_object_state(caller)
    exit_state = flow_execution.get_object_state(exit)
    dest_state = flow_execution.get_object_state(destination)

    if caller_state is None or exit_state is None or dest_state is None:
        msg = "Invalid caller, exit, or destination."
        raise CommandError(msg)

    # Use Evennia's at_traverse hook for compatibility
    if hasattr(exit_state.obj, "at_traverse"):
        try:
            exit_state.obj.at_traverse(caller_state.obj, dest_state.obj)
        except Exception as e:
            if hasattr(exit_state.obj, "at_failed_traverse"):
                exit_state.obj.at_failed_traverse(caller_state.obj)
            else:
                msg = "You cannot go that way."
                raise CommandError(msg) from e
    else:
        # Fallback to simple movement
        success = caller_state.obj.move_to(dest_state.obj, quiet=False)
        if not success:
            msg = "You cannot go that way."
            raise CommandError(msg)


hooks = {
    "move_object": move_object,
    "check_exit_traversal": check_exit_traversal,
    "traverse_exit": traverse_exit,
}
