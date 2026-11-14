"""Accept the changes to the aura (#5123): the second way out of being unsettled.

``AcceptAuraChangeAction`` moves who the character is to where they have got to. The web
aura endpoint and telnet ``aura accept`` converge here. World imports are lazy inside
``execute()``: the action registry is imported very early and the magic models pull in
much of the world graph.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext

_NO_CHARACTER = "You have no aura to settle."


@dataclass
class AcceptAuraChangeAction(Action):
    """Accept the changes to the aura: settle who the character has become.

    Refused unless the character is unsettled. Takes no kwargs.
    """

    key: str = "accept_aura_change"
    name: str = "Accept the changes to your Aura"
    icon: str = "sparkles"
    category: str = "magic"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.magic.exceptions import NotUnsettledError  # noqa: PLC0415
        from world.magic.services.drift import accept_aura_change  # noqa: PLC0415

        sheet = actor.character_sheet
        if sheet is None:
            return ActionResult(success=False, message=_NO_CHARACTER)
        try:
            result = accept_aura_change(sheet)
        except NotUnsettledError as exc:
            return ActionResult(success=False, message=exc.user_message)
        # The affinity they grew toward (what made them unsettled), not the unchanged main one.
        if result.grown_affinity is None:
            message = "You accept the changes to your aura."
        else:
            message = f"You become more {result.grown_affinity.name.lower()}."
        return ActionResult(success=True, message=message, data={"accept_aura_result": result})
