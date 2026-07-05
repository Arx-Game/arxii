"""Bind Companion action (#672) — attempt to bind a wild beast as a companion."""

from __future__ import annotations

from dataclasses import dataclass

from actions.base import Action
from actions.constants import ActionCategory
from actions.prerequisites import HasCompanionCapacityPrerequisite, Prerequisite
from actions.types import ActionResult, TargetType


@dataclass
class BindCompanionAction(Action):
    key: str = "bind_companion"
    name: str = "Bind Companion"
    icon: str = "paw"
    category: str = "companions"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [HasCompanionCapacityPrerequisite()]

    def execute(self, actor, context=None, **kwargs) -> ActionResult:
        from world.checks.models import CheckType  # noqa: PLC0415
        from world.checks.services import perform_check  # noqa: PLC0415
        from world.companions.content import BIND_ATTEMPT_CHECK_NAME  # noqa: PLC0415
        from world.companions.models import CompanionArchetype  # noqa: PLC0415
        from world.companions.services import bind_companion  # noqa: PLC0415
        from world.magic.models.gifts import Gift  # noqa: PLC0415

        gift_id = kwargs.get("gift_id")
        archetype_id = kwargs.get("archetype_id")
        name = kwargs.get("name")
        if not gift_id or not archetype_id or not name:
            return ActionResult(success=False, message="Pick a gift, an archetype, and a name.")

        gift = Gift.objects.get(pk=gift_id)
        archetype = CompanionArchetype.objects.get(pk=archetype_id)
        sheet = actor.sheet_data
        check_type = CheckType.objects.get(name=BIND_ATTEMPT_CHECK_NAME)

        result = perform_check(actor, check_type, target_difficulty=archetype.bind_difficulty)
        if result.outcome is None or result.outcome.success_level < 0:
            return ActionResult(
                success=False,
                message=f"The {archetype.name} resists your attempt to bind it.",
            )

        companion = bind_companion(owner=sheet, archetype=archetype, granting_gift=gift, name=name)
        return ActionResult(
            success=True,
            message=f"{name} the {archetype.name} is now bonded to you.",
            data={"companion_id": companion.pk},
        )
