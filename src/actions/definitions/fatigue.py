"""Fatigue-related player actions.

``RestAction`` is the single ``action.run()`` seam for the daily rest command:
spend AP to gain ``well_rested`` for the next dawn reset. Shared by telnet
``CmdRest`` and the web ``RestView``.
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
class RestAction(Action):
    """Spend AP to rest, gaining well_rested for the next dawn reset.

    The action resolves the actor's character sheet and delegates to
    ``world.fatigue.services.rest``. Failure reasons (already rested today,
    insufficient AP, missing sheet) are returned as a failure
    :class:`~actions.types.ActionResult` so both telnet and web surfaces share
    the same messages and behavior.
    """

    key: str = "rest"
    name: str = "Rest"
    icon: str = "bed"
    category: str = "vitals"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from world.fatigue.services import rest  # noqa: PLC0415

        try:
            sheet = actor.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            return ActionResult(success=False, message="No active character.")

        result = rest(sheet)
        return ActionResult(success=result.success, message=result.message)
