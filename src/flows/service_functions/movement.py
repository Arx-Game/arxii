"""Movement-related service functions."""

from commands.exceptions import CommandError
from flows.object_states.base_state import BaseState


def move_object(
    obj: BaseState,
    destination: BaseState,
    quiet: bool = True,
    **kwargs: object,
) -> None:
    """Move an object to ``destination``.

    Args:
        obj: State of the object to move.
        destination: State of the destination.
        quiet: Passed to ``move_to`` to suppress hooks and messages.
        **kwargs: Additional keyword arguments for ``move_to``.

    Raises:
        CommandError: If the move cannot be completed.
    """
    if not obj.can_move(obj, destination):
        msg = "Move not permitted."
        raise CommandError(msg)

    # Clean up place presences before moving
    from world.scenes.place_services import (  # noqa: PLC0415
        clear_place_presence_for_character,
    )

    clear_place_presence_for_character(obj.obj)

    success = obj.obj.move_to(destination.obj, quiet=quiet, **kwargs)

    if not success:
        msg = "Could not move object."
        raise CommandError(msg)


def check_exit_traversal(
    caller: BaseState,
    exit: BaseState,  # noqa: A002
    **kwargs: object,
) -> None:
    """Check if the caller can traverse the exit.

    Args:
        caller: State of the character attempting traversal.
        exit: State of the exit being traversed.
        **kwargs: Additional keyword arguments.

    Raises:
        CommandError: If traversal is not permitted.
    """
    if not exit.can_traverse(caller):
        msg = "You cannot go that way."
        raise CommandError(msg)

    # Check if the exit has a destination
    if not hasattr(exit.obj, "destination") or not exit.obj.destination:
        msg = "That exit doesn't lead anywhere."
        raise CommandError(msg)


def traverse_exit(
    caller: BaseState,
    exit: BaseState,  # noqa: A002
    destination: BaseState,
    **kwargs: object,
) -> None:
    """Move the caller through the exit to its destination.

    Args:
        caller: State of the character.
        exit: State of the exit.
        destination: State of the destination.
        **kwargs: Additional keyword arguments.

    Raises:
        CommandError: If the traversal cannot be completed.
    """
    # Use Evennia's at_traverse hook for compatibility
    if hasattr(exit.obj, "at_traverse"):
        try:
            exit.obj.at_traverse(caller.obj, destination.obj)
        except Exception as e:
            if hasattr(exit.obj, "at_failed_traverse"):
                exit.obj.at_failed_traverse(caller.obj)
            else:
                msg = "You cannot go that way."
                raise CommandError(msg) from e
    else:
        # Fallback to simple movement
        success = caller.obj.move_to(destination.obj, quiet=False)
        if not success:
            msg = "You cannot go that way."
            raise CommandError(msg)


hooks = {
    "move_object": move_object,
    "check_exit_traversal": check_exit_traversal,
    "traverse_exit": traverse_exit,
}
