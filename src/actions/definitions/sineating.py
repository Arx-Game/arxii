"""Sineating actions (#5177): the Sinner's plea, the Sineater's ritual and a refusal.

Telnet ``pose/entreat`` and ``pose/sineat`` and the web pose composer both end here, after
the pose that carries the act is posted (``run_pose_sineating``). ``DeclineSineatingAction``
turns a waiting plea down without a pose.

World imports are lazy inside ``execute()``: the action registry is imported very early and
the magic models pull in much of the world graph.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext
    from world.magic.types.soul_tether import PendingSineating

_NO_SHEET = "You have no character sheet."
_NO_PARTNER = "Name the character to ask."


def _run_part(actor: ObjectDB, role: str, kwargs: dict[str, Any]) -> ActionResult:
    """Check and carry out one part of a Sineating for ``actor``; the lines are theirs."""
    from world.magic.exceptions import SoulTetherError  # noqa: PLC0415
    from world.magic.services.sineating import (  # noqa: PLC0415
        pending_sineating_from,
        record_pending_sineating,
    )

    sheet = actor.character_sheet
    if sheet is None:
        return ActionResult(success=False, message=_NO_SHEET)
    try:
        pending = pending_sineating_from(
            sheet,
            {
                "sineating_role": role,
                "sineating_partner_id": kwargs.get("partner_sheet_id"),
                "sineating_units": kwargs.get("units"),
            },
        )
        lines = record_pending_sineating(pending) if pending is not None else ()
    except SoulTetherError as exc:
        return ActionResult(success=False, message=exc.user_message)
    return ActionResult(
        success=True, message="\n".join(lines), data={"sineating_lines": list(lines)}
    )


@dataclass
class EntreatSineatingAction(Action):
    """The Sinner asks a Sineater to take on their sins.

    kwargs:
        partner_sheet_id: the Sineater's character sheet id.
        units: how many units of Sineating to offer.

    Writes the plea and tells the Sineater a plea waits; the room is told nothing.
    """

    key: str = "entreat_sineating"
    name: str = "Entreat a Sineater"
    icon: str = "sparkles"
    category: str = "magic"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.magic.constants import SineatingPoseRole  # noqa: PLC0415

        return _run_part(actor, SineatingPoseRole.ENTREAT, kwargs)


@dataclass
class PerformSineatingAction(Action):
    """The Sineater performs the ritual for a Sinner's waiting plea and rolls for it.

    kwargs:
        partner_sheet_id: the Sinner's character sheet id.
        units: how many of the offered units to take on.

    Moves corruption and pays both parties; the Sinner is told what happened privately and the
    result lines returned are the Sineater's.
    """

    key: str = "perform_sineating"
    name: str = "Perform Sineating"
    icon: str = "sparkles"
    category: str = "magic"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.magic.constants import SineatingPoseRole  # noqa: PLC0415

        return _run_part(actor, SineatingPoseRole.PERFORM, kwargs)


@dataclass
class DeclineSineatingAction(Action):
    """The Sineater turns down a Sinner's waiting plea.

    kwargs:
        partner_sheet_id: the Sinner's character sheet id.
    """

    key: str = "decline_sineating"
    name: str = "Decline a plea for Sineating"
    icon: str = "x"
    category: str = "magic"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
        from world.magic.exceptions import SoulTetherError  # noqa: PLC0415
        from world.magic.services.sineating import decline_sineating  # noqa: PLC0415

        sheet = actor.character_sheet
        if sheet is None:
            return ActionResult(success=False, message=_NO_SHEET)
        sinner = CharacterSheet.objects.filter(pk=kwargs.get("partner_sheet_id")).first()
        if sinner is None:
            return ActionResult(success=False, message=_NO_PARTNER)
        try:
            decline_sineating(sinner, sheet)
        except SoulTetherError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True, message=f"You decline {sinner.primary_persona.name}'s plea."
        )


def run_pose_sineating(actor: ObjectDB, pending: PendingSineating) -> tuple[str, bool]:
    """Carry out the Sineating a posted pose carried; returns the lines the writer reads and
    whether it happened.

    The pose cannot be un-posted, so a refusal here becomes a line saying the pose stands and
    why nothing happened.
    """
    from world.magic.constants import SineatingPoseRole  # noqa: PLC0415

    entreat = pending.role == SineatingPoseRole.ENTREAT
    partner = pending.sineater_sheet if entreat else pending.sinner_sheet
    action: Action = EntreatSineatingAction() if entreat else PerformSineatingAction()
    result = action.run(actor, partner_sheet_id=partner.pk, units=pending.units)
    if result.success:
        return result.message or "", True
    return (
        f"Your pose was posted, but the Sineating did not happen: {result.message}",
        False,
    )
