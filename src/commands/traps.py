"""Telnet face of ``DisarmTrapAction`` (#3011) — the player half of the trap loop.

Thin over ``DisarmTrapAction``, mirrored against how ``search`` already lists
traps a character has detected: ``disarm <trap name>`` resolves the trap by
name among the traps this caller can currently see (armed, and either
``is_hidden=False`` or already in their own ``detected_by`` — the same
visibility rule ``RoomTrapViewSet`` enforces on the web) and dispatches
``action.run()``. No business logic here — resolving a name to a trap id is
the only work a telnet command ever does.
"""

from __future__ import annotations

from typing import Any

from django.db.models import Q

from actions.definitions.traps import DisarmTrapAction
from commands.command import ArxCommand
from commands.exceptions import CommandError

_MSG_WHICH_TRAP = "Disarm which trap? Usage: disarm <trap name>"


def visible_traps(actor: Any) -> Any:
    """Every armed trap ``actor`` can currently see in their own room.

    Mirrors ``RoomTrapViewSet``'s leak table: not-hidden, or already recorded
    in the actor's own ``detected_by``. An actor with no location or no
    character sheet sees none.
    """
    from world.room_features.models import Trap  # noqa: PLC0415

    if actor.location is None:
        return Trap.objects.none()
    sheet = actor.character_sheet
    if sheet is None:
        return Trap.objects.none()
    return Trap.objects.filter(room_profile_id=actor.location.pk, is_armed=True).filter(
        Q(is_hidden=False) | Q(detected_by=sheet)
    )


class CmdDisarm(ArxCommand):
    """Disarm a trap you can see in your current room.

    Usage:
      disarm <trap name>

    A failed disarm sets the trap off on you — the same risk as walking into
    one, just deliberately chosen.
    """

    key = "disarm"
    locks = "cmd:all()"
    help_category = "General"
    action = DisarmTrapAction()

    def resolve_action_args(self) -> dict[str, Any]:
        name = self.require_args(_MSG_WHICH_TRAP)
        trap = visible_traps(self.caller).filter(name__iexact=name).first()
        if trap is None:
            not_found_msg = f"There is no such trap here as '{name}'."
            raise CommandError(not_found_msg)
        return {"trap_id": trap.pk}
