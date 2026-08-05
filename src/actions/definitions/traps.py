"""Trap interaction actions (#1051, #520 Phase 6)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.prerequisites import (
    IsSceneGMPrerequisite,
    MinimumGMLevelPrerequisite,
    Prerequisite,
)
from actions.types import ActionResult, TargetType
from world.checks.consequence_resolution import (
    apply_resolution,
    resolve_pool_consequences,
    select_consequence,
)
from world.checks.types import ResolutionContext
from world.gm.constants import GMLevel

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext


@dataclass
class DisarmTrapAction(Action):
    """Attempt to disarm an armed trap in the actor's current room.

    Routes the trap's ``consequence_pool`` through ``disarm_check_type``: a
    success-tier roll disarms the trap (it carries no damage consequence at that
    tier), while a failure-tier roll fires the authored damage on the would-be
    disarmer — failing to disarm sets the trap off.
    """

    key: str = "disarm_trap"
    name: str = "Disarm Trap"
    icon: str = "bomb"
    category: str = "exploration"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.room_features.models import Trap  # noqa: PLC0415

        trap_id = kwargs.get("trap_id")
        if trap_id is None:
            return ActionResult(success=False, message="Disarm which trap?")

        trap = Trap.objects.filter(pk=trap_id, is_armed=True).first()
        if trap is None:
            return ActionResult(success=False, message="There is no such armed trap here.")
        if trap.room_profile.objectdb != actor.location:
            return ActionResult(success=False, message="That trap is not here.")

        consequences = resolve_pool_consequences(trap.consequence_pool)
        pending = select_consequence(
            actor, trap.disarm_check_type, trap.disarm_difficulty, consequences
        )
        outcome = pending.check_result.outcome
        disarmed = outcome is not None and outcome.success_level > 0

        trap.detected_by.add(actor.sheet_data)
        if disarmed:
            trap.is_armed = False
            trap.save(update_fields=["is_armed"])
            return ActionResult(success=True, message=f"You disarm {trap.name}.")

        # Failed disarm - the trap goes off on the would-be disarmer.
        apply_resolution(pending, ResolutionContext(character=actor, target=actor))
        return ActionResult(
            success=False,
            message=f"You trigger {trap.name} while trying to disarm it!",
        )


_MSG_NO_ROOM = "You have no location."
_MSG_WHICH_TRAP = "Which trap? (try `gm trap list`)"
_MSG_NO_SUCH_TRAP = "There is no such trap here."


def _gm_trap_prerequisites() -> list[Prerequisite]:
    """The gate every GM trap action shares.

    JUNIOR matches ``SetSituationAction``, which already mints armed traps, so
    acting on one that already exists is strictly less powerful. The scene gate
    is on top of it because listing traps reveals hidden room content and a GM
    is also a player: trust alone would let any JUNIOR GM stand in someone
    else's dungeon and read its hazards. Both carry a staff bypass.
    """
    return [MinimumGMLevelPrerequisite(GMLevel.JUNIOR), IsSceneGMPrerequisite()]


def _room_traps(actor: ObjectDB):
    """Every trap in the actor's current room, ordered by the model's own Meta.

    ``RoomProfile`` is a ``primary_key=True`` OneToOne onto ``ObjectDB``
    (``evennia_extensions/models.py:549``), so ``room_profile_id`` is the room's
    own pk and this needs no join.
    """
    from world.room_features.models import Trap  # noqa: PLC0415

    if actor.location is None:
        return Trap.objects.none()
    return Trap.objects.filter(room_profile_id=actor.location.pk).select_related("position")


def _resolve_trap_in_room(actor: ObjectDB, trap_id: Any) -> tuple[Any, str | None]:
    """Resolve ``trap_id`` to a Trap in the actor's room, or return a refusal.

    Room-scoped so a GM cannot reach a trap they are not standing with, mirroring
    ``StagePropertyAction``'s ``db_location`` scoping.
    """
    if actor.location is None:
        return None, _MSG_NO_ROOM
    if trap_id is None:
        return None, _MSG_WHICH_TRAP
    try:
        pk = int(trap_id)
    except (TypeError, ValueError):
        return None, _MSG_NO_SUCH_TRAP
    trap = _room_traps(actor).filter(pk=pk).first()
    if trap is None:
        return None, _MSG_NO_SUCH_TRAP
    return trap, None


def _set_armed(actor: ObjectDB, trap_id: Any, *, armed: bool, verb: str) -> ActionResult:
    """Shared body for arm/disarm: resolve in-room, flip the flag, report."""
    trap, error = _resolve_trap_in_room(actor, trap_id)
    if error is not None:
        return ActionResult(success=False, message=error)
    trap.is_armed = armed
    trap.save(update_fields=["is_armed"])
    return ActionResult(
        success=True,
        message=f"You {verb} {trap.name}.",
        data={"trap_id": trap.pk, "is_armed": armed},
    )


@dataclass
class ListRoomTrapsAction(Action):
    """GM: list every trap in the actor's room, armed or not (#3002).

    The prerequisite for the other two verbs, and for trap management at all:
    nothing else anywhere hands out a trap id.
    """

    key: str = "list_room_traps"
    name: str = "List Room Traps"
    icon: str = "list"
    category: str = "gm"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return _gm_trap_prerequisites()

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        if actor.location is None:
            return ActionResult(success=False, message=_MSG_NO_ROOM)
        rows = [
            {
                "id": trap.pk,
                "name": trap.name,
                "is_armed": trap.is_armed,
                "position": trap.position.name if trap.position_id else None,
            }
            for trap in _room_traps(actor)
        ]
        if not rows:
            return ActionResult(success=True, message="No traps here.", data={"traps": []})
        lines = [
            f"[{row['id']}] {row['name']} - {'armed' if row['is_armed'] else 'disarmed'}"
            + (f" @ {row['position']}" if row["position"] else "")
            for row in rows
        ]
        return ActionResult(success=True, message="\n".join(lines), data={"traps": rows})


@dataclass
class ArmTrapAction(Action):
    """GM: arm or re-arm a trap in the actor's room (#3002).

    Deliberately does NOT clear ``detected_by``. A character who already found
    this trap knows where it is; clearing that would silently re-hide a hazard
    from someone who earned the knowledge. A re-armed trap fires for newcomers
    and stays inert for those who already resolved it.
    """

    key: str = "arm_trap"
    name: str = "Arm Trap"
    icon: str = "bomb"
    category: str = "gm"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return _gm_trap_prerequisites()

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        return _set_armed(actor, kwargs.get("trap_id"), armed=True, verb="arm")


@dataclass
class GmDisarmTrapAction(Action):
    """GM: switch a trap off with no roll (#3002).

    Distinct from the player's ``DisarmTrapAction``, which rolls
    ``disarm_check_type`` and fires the trap on the roller when it fails. A GM
    turning a hazard off mid-scene needs a switch, not a gamble.
    """

    key: str = "gm_disarm_trap"
    name: str = "GM Disarm Trap"
    icon: str = "shield-check"
    category: str = "gm"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return _gm_trap_prerequisites()

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        return _set_armed(actor, kwargs.get("trap_id"), armed=False, verb="disarm")
