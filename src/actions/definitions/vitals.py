"""Vitals lifecycle actions: waking from unconsciousness (#2287).

The retire and death-kudos actions from the same issue also live here.
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
class WakeAction(Action):
    """Attempt to wake from unconsciousness (one check per round)."""

    key: str = "wake"
    name: str = "Wake"
    icon: str = "sunrise"
    category: str = "vitals"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from world.vitals.services import attempt_wake  # noqa: PLC0415

        try:
            sheet = actor.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            sheet = None
        if sheet is None:
            return ActionResult(success=False, message="You are already awake.")
        result = attempt_wake(sheet)
        return ActionResult(success=result.woke, message=result.message)
