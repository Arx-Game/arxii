"""JUNIOR-GM-tier Action: instantiate a SituationTemplate into the actor's room (#1895)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.core.exceptions import ObjectDoesNotExist
from evennia.objects.models import ObjectDB

from actions.base import Action
from actions.constants import ActionCategory
from actions.prerequisites import MinimumGMLevelPrerequisite
from actions.types import ActionContext, ActionResult, TargetType
from world.gm.constants import GMLevel
from world.mechanics.models import SituationTemplate
from world.mechanics.situation_services import instantiate_situation


@dataclass
class SetSituationAction(Action):
    """JUNIOR-tier GM action: instantiate a SituationTemplate into the actor's current room.

    Dispatch convention
    -------------------
    REGISTRY ActionRef: ``registry_key="set_situation"``,
    ``situation_template_id=<SituationTemplate.pk>``.

    Gated on ``MinimumGMLevelPrerequisite(GMLevel.JUNIOR)`` (#2117; staff
    bypass preserved) -- this mints live ``Challenge``/``ChallengeInstance``
    rows (ADR-0091), one tier above bare approval.
    """

    key: str = "set_situation"
    name: str = "Set Situation"
    icon: str = "map"
    category: str = "gm"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list:
        return [MinimumGMLevelPrerequisite(GMLevel.JUNIOR)]

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

        try:
            instantiate_situation(template, actor.location)
        except ObjectDoesNotExist:
            return ActionResult(
                success=False,
                message="This room isn't set up to hold that situation's traps.",
            )

        return ActionResult(success=True)
