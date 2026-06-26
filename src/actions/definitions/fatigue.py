"""Fatigue-related player actions.

``RestAction`` is the single ``action.run()`` seam for the daily rest command:
spend AP to gain ``well_rested`` for the next dawn reset. Shared by telnet
``CmdRest`` and the web ``RestView``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.prerequisites import Prerequisite
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext


@dataclass
class CanRestPrerequisite(Prerequisite):
    """Rest is only usable at the actor's own home and outside of combat."""

    def is_met(
        self,
        actor: ObjectDB,
        target: ObjectDB | None = None,
        context: dict | None = None,
    ) -> tuple[bool, str]:
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from actions.round_context import get_active_round_context  # noqa: PLC0415
        from world.combat.round_context import CombatRoundContext  # noqa: PLC0415

        try:
            sheet = actor.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            return False, "No active character."

        round_context = get_active_round_context(sheet)
        if isinstance(round_context, CombatRoundContext):
            return False, "You cannot rest while in combat."

        if actor.location != actor.home:
            return False, "You can only rest at home."

        return True, ""


@dataclass
class RestAction(Action):
    """Spend AP to rest, gaining well_rested for the next dawn reset.

    The action resolves the actor's character sheet, checks that they are not
    in combat and are at their own home, and delegates to
    ``world.fatigue.services.rest``. Failure reasons (not at home, in combat,
    already rested today, insufficient AP, missing sheet) are returned as a
    failure :class:`~actions.types.ActionResult` so both telnet and web
    surfaces share the same messages and behavior.
    """

    key: str = "rest"
    name: str = "Rest"
    icon: str = "bed"
    category: str = "vitals"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [CanRestPrerequisite()]

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
