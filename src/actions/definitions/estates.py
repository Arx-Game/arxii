"""Estate actions: the executor's will-reading door (#1985).

Telnet and web dispatch converge on ``action.run()``; the reading is one of
the three settlement doors (funeral finish and the deadline sweeper are the
others), all delegating to ``world.estates.services.execute_settlement``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext


@dataclass
class WillReadingAction(Action):
    """Read the deceased's testament aloud and execute their estate.

    Any one persona tagged as a ``WillExecutor`` on the deceased's will may
    perform the reading while the settlement is PENDING. The testament is
    emitted to the actor's location; the estate executes through the single
    idempotent settlement path (an already-settled estate refuses politely).
    """

    key: str = "will_reading"
    name: str = "Hold a Will-Reading"
    icon: str = "scroll"
    category: str = "estates"
    target_type: TargetType = TargetType.SINGLE

    def execute(  # noqa: PLR0911 - one refusal message per gate, deliberately flat
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from world.estates.constants import SettlementDoor, SettlementStatus  # noqa: PLC0415
        from world.estates.models import EstateSettlement, Will, WillExecutor  # noqa: PLC0415
        from world.estates.services import execute_settlement  # noqa: PLC0415

        target_name = kwargs.get("target_name")
        if not target_name:
            return ActionResult(success=False, message="Whose will is being read?")
        found = actor.search(target_name, global_search=True, quiet=True)
        target = found[0] if found else None
        if target is None:
            return ActionResult(success=False, message=f"No character '{target_name}' found.")
        try:
            deceased_sheet = target.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            deceased_sheet = None
        if deceased_sheet is None:
            return ActionResult(success=False, message="They have no character sheet.")

        will = Will.objects.filter(character_sheet=deceased_sheet).first()
        if will is None:
            return ActionResult(success=False, message="They left no will to read.")
        try:
            actor_sheet = actor.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            actor_sheet = None
        if (
            actor_sheet is None
            or not WillExecutor.objects.filter(
                will=will, persona__character_sheet=actor_sheet
            ).exists()
        ):
            return ActionResult(
                success=False, message="You are not named as an executor of that will."
            )
        settlement = EstateSettlement.objects.filter(character_sheet=deceased_sheet).first()
        if settlement is None or settlement.status != SettlementStatus.PENDING:
            return ActionResult(success=False, message="That estate has already been settled.")

        execute_settlement(deceased_sheet, via=SettlementDoor.READING)
        if actor.location is not None:
            # PLACEHOLDER framing copy — Apostate rewrite pending (#1985).
            testament = will.testament_text or "The will is read; its terms are carried out."
            actor.location.msg_contents(f"{actor.key} reads the will of {target.key}:\n{testament}")
        return ActionResult(success=True, message="The will is read; the estate is settled.")
