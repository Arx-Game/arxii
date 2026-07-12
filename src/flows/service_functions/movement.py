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

    # #2051: capture origin before the move — move_to relocates obj.obj.location,
    # so the origin room is lost after the move. Needed to revalidate the
    # remaining origin-room occupants whose covenant vows may have dimmed
    # because the mover (a covenant-mate) just left.
    origin = obj.obj.location

    success = obj.obj.move_to(destination.obj, quiet=quiet, **kwargs)

    if not success:
        msg = "Could not move object."
        raise CommandError(msg)

    # Auto-engage Durance covenant if co-present with members (Slice B §4.10)
    sheet = getattr(obj.obj, "sheet_data", None)  # noqa: GETATTR_LITERAL
    if sheet is not None and obj.obj.location is not None:
        from world.covenants.services import (  # noqa: PLC0415
            evaluate_scene_engagement,
            revalidate_engagements,
        )

        evaluate_scene_engagement(character_sheet=sheet, room=obj.obj.location)
        # #2051: revalidate the mover's own vows at the new location —
        # co-presence may have changed for them too (e.g. left their covenant).
        revalidate_engagements(character_sheet=sheet, room=obj.obj.location)

    # #2051: revalidate remaining origin-room occupants whose vows may have
    # dimmed because the mover (a covenant-mate) just left. Hot path:
    # short-circuit via cached handlers — only touch occupants with an engaged
    # covenant role (the common case of no covenant membership touches no DB).
    if origin is not None:
        from world.covenants.services import revalidate_engagements  # noqa: PLC0415

        for remaining in origin.contents:
            remaining_sheet = getattr(remaining, "sheet_data", None)  # noqa: GETATTR_LITERAL
            if remaining_sheet is None:
                continue
            roles = remaining_sheet.character.covenant_roles
            if not any(m.engaged for m in roles.active_memberships):
                continue
            revalidate_engagements(character_sheet=remaining_sheet, room=origin)


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

    # #2177: react to ward/alarm on successful entry. Guard on actual
    # arrival (not just "no exception raised") because the pre-existing
    # at_traverse-exception branch above falls through to here without
    # returning when at_failed_traverse exists -- this task doesn't change
    # that existing control flow, only avoids reacting on a failed move.
    if caller.obj.location == destination.obj:
        from world.room_features.services import react_to_unauthorized_entry  # noqa: PLC0415

        react_to_unauthorized_entry(caller.obj, destination.obj)


hooks = {
    "move_object": move_object,
    "check_exit_traversal": check_exit_traversal,
    "traverse_exit": traverse_exit,
}
