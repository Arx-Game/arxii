"""Single-actor covenant lifecycle REGISTRY actions — the action.run() seam
for engage/disengage/leave/kick/rank/transfer/stand-down (#1346).

Thin wrappers over world.covenants.services; the web viewsets call the same
services directly. CovenantError → failure ActionResult(exc.user_message)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext


def _run_service(mutation: Callable[[], None], success_message: str) -> ActionResult:
    """Run a covenant service mutation, mapping CovenantError → failure result.

    Shared by every covenant Action whose only failure mode is a service-raised
    ``CovenantError`` (the curated ``user_message`` is surfaced verbatim)."""
    from world.covenants.exceptions import CovenantError  # noqa: PLC0415

    try:
        mutation()
    except CovenantError as exc:
        return ActionResult(success=False, message=exc.user_message)
    return ActionResult(success=True, message=success_message)


@dataclass
class EngageCovenantMembershipAction(Action):
    """Engage a character's covenant role for the current scene."""

    key: str = "engage_covenant_membership"
    name: str = "Engage Covenant"
    icon: str = "shield"
    category: str = "covenant"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.covenants.exceptions import (  # noqa: PLC0415
            CovenantEngagementPrerequisiteNotMetError,
        )
        from world.covenants.handlers import can_engage_membership  # noqa: PLC0415
        from world.covenants.services import set_engaged_membership  # noqa: PLC0415

        membership = kwargs["membership"]
        if not can_engage_membership(membership):
            return ActionResult(
                success=False,
                message=CovenantEngagementPrerequisiteNotMetError.user_message,
            )
        set_engaged_membership(membership=membership)
        return ActionResult(success=True, message="You engage your covenant role.")


@dataclass
class DisengageCovenantMembershipAction(Action):
    """Disengage a character's covenant role."""

    key: str = "disengage_covenant_membership"
    name: str = "Disengage Covenant"
    icon: str = "shield-off"
    category: str = "covenant"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.covenants.services import clear_engaged_membership  # noqa: PLC0415

        clear_engaged_membership(membership=kwargs["membership"])
        return ActionResult(success=True, message="You disengage your covenant role.")


@dataclass
class LeaveCovenantAction(Action):
    """Voluntarily leave a covenant."""

    key: str = "leave_covenant"
    name: str = "Leave Covenant"
    icon: str = "door-open"
    category: str = "covenant"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.covenants.services import leave_covenant  # noqa: PLC0415

        return _run_service(
            lambda: leave_covenant(membership=kwargs["membership"]),
            "You leave the covenant.",
        )


@dataclass
class KickCovenantMemberAction(Action):
    """Remove a member from a covenant by rank authority."""

    key: str = "kick_covenant_member"
    name: str = "Kick Covenant Member"
    icon: str = "user-minus"
    category: str = "covenant"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.covenants.services import kick_member  # noqa: PLC0415

        return _run_service(
            lambda: kick_member(target=kwargs["target"], actor=kwargs["actor_membership"]),
            "You remove them from the covenant.",
        )


@dataclass
class AssignCovenantRankAction(Action):
    """Assign a rank to a covenant member."""

    key: str = "assign_covenant_rank"
    name: str = "Assign Covenant Rank"
    icon: str = "crown"
    category: str = "covenant"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.covenants.services import assign_rank  # noqa: PLC0415

        return _run_service(
            lambda: assign_rank(
                membership=kwargs["membership"],
                actor=kwargs["actor_membership"],
                rank=kwargs["rank"],
            ),
            "Rank assigned.",
        )


@dataclass
class TransferTopRankAction(Action):
    """Transfer the top rank of a covenant to another member."""

    key: str = "transfer_covenant_top_rank"
    name: str = "Transfer Top Rank"
    icon: str = "flag"
    category: str = "covenant"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.covenants.services import transfer_top  # noqa: PLC0415

        return _run_service(
            lambda: transfer_top(
                covenant=kwargs["covenant"],
                actor=kwargs["actor_membership"],
                new_top_membership=kwargs["new_top_membership"],
            ),
            "The top rank passes to them.",
        )


@dataclass
class StandDownBattleCovenantAction(Action):
    """Stand down a battle covenant, ending its active status."""

    key: str = "stand_down_battle_covenant"
    name: str = "Stand Down"
    icon: str = "flag-off"
    category: str = "covenant"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.covenants.services import stand_down_battle_covenant  # noqa: PLC0415

        return _run_service(
            lambda: stand_down_battle_covenant(covenant=kwargs["covenant"]),
            "The banners are lowered; the covenant stands down.",
        )
