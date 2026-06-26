"""Condition-related player actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.constants import ActionCategory, TargetKind
from actions.types import ActionContext, ActionResult, TargetFilters, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


@dataclass
class TreatConditionAction(Action):
    """Offer to treat another character's condition or pending alteration."""

    key: str = "treat_condition"
    name: str = "Treat Condition"
    icon: str = "heart-pulse"
    category: str = "condition"
    target_type: TargetType = TargetType.SINGLE
    target_kind: TargetKind | None = TargetKind.PERSONA
    target_filters: TargetFilters | None = None
    action_category: ActionCategory | None = ActionCategory.SOCIAL
    costs_turn: bool = True

    def __post_init__(self) -> None:
        self.target_filters = TargetFilters(in_same_scene=True, exclude_self=True)

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        """Direct execution path is not used by the consent flow.

        The telnet/web surfaces create a SceneActionRequest via
        create_action_request. If something calls run() directly, fail clearly.
        """
        return ActionResult(
            success=False,
            message="Use the scene treatment request flow to treat another character.",
        )


treat_condition = TreatConditionAction()
