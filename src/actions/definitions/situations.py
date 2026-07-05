"""Staff-only Action: instantiate a SituationTemplate into the actor's room (#1895)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from evennia.objects.models import ObjectDB

from actions.base import Action
from actions.constants import ActionCategory
from actions.prerequisites import StaffOnlyPrerequisite
from actions.types import ActionContext, ActionResult, TargetType
from world.mechanics.models import SituationTemplate
from world.mechanics.situation_services import instantiate_situation


@dataclass
class SetSituationAction(Action):
    """Staff-only action: instantiate a SituationTemplate into the actor's current room.

    Dispatch convention
    -------------------
    REGISTRY ActionRef: ``registry_key="set_situation"``,
    ``situation_template_id=<SituationTemplate.pk>``.
    """

    key: str = "set_situation"
    name: str = "Set Situation"
    icon: str = "map"
    category: str = "gm"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list:
        return [StaffOnlyPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        template_id = kwargs.get("situation_template_id")
        if template_id is None:
            return ActionResult(success=False, message="Set which situation?")

        try:
            template = SituationTemplate.objects.get(pk=template_id)
        except SituationTemplate.DoesNotExist:
            return ActionResult(success=False, message="That situation template does not exist.")

        instantiate_situation(template, actor.location)

        return ActionResult(success=True)
