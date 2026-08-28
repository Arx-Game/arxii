"""Movement-related service functions."""

import logging

from evennia.objects.models import ObjectDB

from commands.exceptions import CommandError
from flows.object_states.base_state import BaseState

logger = logging.getLogger(__name__)


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
    sheet = obj.obj.character_sheet
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
            remaining_sheet = remaining.character_sheet
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

    # Encumbrance hard stop (#2862): ONLY the extreme combination refuses —
    # far-too-heavy load AND an exhausted physical pool — and the message
    # names both causes so nobody is ever mysteriously stuck.
    from world.items.services.encumbrance import movement_blocked_message  # noqa: PLC0415

    blocked = movement_blocked_message(caller.obj)
    if blocked is not None:
        raise CommandError(blocked)

    # Check if the exit has a destination
    if not hasattr(exit.obj, "destination") or not exit.obj.destination:
        msg = "That exit doesn't lead anywhere."
        raise CommandError(msg)

    # #2989 — the unresistable expulsion bar. Pre-traversal (not post-arrival
    # like guard detection/ward reaction) because a barred character must
    # never even land in the room: no check, no roll, no way around it.
    destination = exit.obj.destination
    barred_sheet = caller.obj.character_sheet
    if barred_sheet is not None:
        from world.npc_services.expulsion_services import active_bar_for  # noqa: PLC0415

        if active_bar_for(destination, barred_sheet) is not None:
            msg = "You are barred from entering there."
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
            # Without this log a real traverse bug reads as a locked door.
            logger.exception("at_traverse failed for exit %s", exit.obj.pk)
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
        from world.items.services.encumbrance import charge_move_fatigue  # noqa: PLC0415
        from world.room_features.services import react_to_unauthorized_entry  # noqa: PLC0415

        react_to_unauthorized_entry(caller.obj, destination.obj)
        # Encumbrance move cost (#2862): free under capacity, always; above
        # it the room costs physical fatigue and says so.
        charge_move_fatigue(caller.obj)


def redirect_move_to_bearer_at_stage(
    *,
    payload: object,
    condition_name: str,
    stage_order: object,
    **kwargs: object,
) -> int | None:
    """Redirect an in-flight move to a random room bearing a condition at a stage.

    General-purpose ``CALL_SERVICE_FUNCTION`` target for authored special
    movement (#3416). Rooms are grouped by putting a condition on them -
    ``ConditionInstance.target`` accepts a room, not just a character - so
    "every room at depth 2 of this labyrinth" is an ordinary queryset over
    authored rows, with no bespoke grouping model.

    Only meaningful on a ``MOVE_PRE_DEPART`` payload, whose ``destination``
    is deliberately mutable; ``Character.move_to`` reads it back and honors
    it. No-ops (leaving the move alone) when nothing matches, so a
    misconfigured stage can never strand a character.

    The bearer's current room is excluded, so a move always *moves*.

    Args:
        payload: The event payload; needs ``character`` and ``destination``.
        condition_name: Condition marking rooms as members of the space.
        stage_order: Which stage (depth) to land in. Usually a flow variable
            (``"@depth"``) produced by ``advance_condition_stage``.

    Returns:
        The chosen room's pk, or ``None`` if the move was left untouched.
    """
    import random  # noqa: PLC0415 - only needed on this path

    from world.conditions.models import ConditionInstance  # noqa: PLC0415

    if stage_order is None:
        return None
    try:
        stage_value = int(stage_order)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return None

    character = payload.character
    here = character.location

    candidate_ids = list(
        ConditionInstance.objects.filter(
            condition__name=condition_name,
            current_stage__stage_order=stage_value,
        )
        .exclude(target_id=here.pk if here is not None else None)
        .values_list("target_id", flat=True)
    )
    if not candidate_ids:
        return None

    # S311 is suppressed deliberately: this is flavour randomness for authored
    # spaces, never a security or fairness boundary. Tests seed `random` so
    # failures reproduce.
    chosen_id = random.choice(candidate_ids)  # noqa: S311
    chosen = ObjectDB.objects.filter(pk=chosen_id).first()
    if chosen is None:
        return None

    payload.destination = chosen
    return chosen_id


def redirect_move(*, payload: object, room_id: object, **kwargs: object) -> bool:
    """Redirect an in-flight move to one specific room (#3416).

    The blunt counterpart to ``redirect_move_to_bearer_at_stage`` - used for
    the "and you are simply out" case (a retreat, an ejection, a threshold
    that always lands somewhere fixed). No-ops if the room can't be resolved.
    """
    try:
        pk = int(room_id)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return False
    room = ObjectDB.objects.filter(pk=pk).first()
    if room is None:
        return False
    payload.destination = room
    return True


hooks = {
    "move_object": move_object,
    "check_exit_traversal": check_exit_traversal,
    "traverse_exit": traverse_exit,
    "redirect_move_to_bearer_at_stage": redirect_move_to_bearer_at_stage,
    "redirect_move": redirect_move,
}
