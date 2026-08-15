"""Divorce action (#2358): unilateral union dissolution + prestige hits.

Thin wrapper over ``world.societies.houses.pact_services.initiate_divorce`` —
either spouse may end a living marriage unilaterally; the service applies
both spouses' prestige hits (initiator steeper) and dissolves the bound
MarriagePact under ``PactDissolutionReason.DIVORCE``.
"""

from dataclasses import dataclass
from typing import Any

from evennia.objects.models import ObjectDB

from actions.base import Action, ActionResult
from actions.prerequisites import HasCharacterSheetPrerequisite, Prerequisite
from actions.types import ActionContext, TargetType


@dataclass
class InitiateDivorceAction(Action):
    """End your own marriage unilaterally (``divorce <union-id>``)."""

    key: str = "initiate_divorce"
    name: str = "Initiate Divorce"
    icon: str = "heart-crack"
    category: str = "houses"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list["Prerequisite"]:
        return [HasCharacterSheetPrerequisite()]

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.roster.models import Union  # noqa: PLC0415
        from world.societies.houses.pact_services import initiate_divorce  # noqa: PLC0415
        from world.societies.houses.services import HousesServiceError  # noqa: PLC0415

        sheet = actor.sheet_data
        union_id = kwargs.get("union_id")
        union = Union.objects.filter(pk=union_id).first() if union_id else None
        if union is None:
            return ActionResult(success=False, message="No such marriage to end.")
        try:
            initiate_divorce(sheet, union)
        except HousesServiceError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(success=True, message="The marriage is ended. Word of it will spread.")
