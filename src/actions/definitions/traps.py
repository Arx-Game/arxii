"""Trap interaction actions (#1051, #520 Phase 6)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionResult, TargetType
from world.checks.consequence_resolution import (
    apply_resolution,
    resolve_pool_consequences,
    select_consequence,
)
from world.checks.types import ResolutionContext

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

        # Failed disarm — the trap goes off on the would-be disarmer.
        apply_resolution(pending, ResolutionContext(character=actor, target=actor))
        return ActionResult(
            success=False,
            message=f"You trigger {trap.name} while trying to disarm it!",
        )
