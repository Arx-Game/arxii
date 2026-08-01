"""GM species-condition grants (#2862 gap close).

``apply_shade_undeath`` shipped with #2853 documented as "the one entry point
story/GM tools use to make someone a shade" — and then had no caller anywhere,
so no Shade could ever exist and the daily-drain half of the appetite economy
could never fire. This is the missing GM tool.

The in-fiction acquisition path (a botched ritual? a soulfray catastrophe? a
death that did not take?) is a design question for ApostateCD; this makes the
condition reachable without inventing lore for it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.constants import ActionCategory
from actions.prerequisites import MinimumGMLevelPrerequisite, Prerequisite
from actions.types import ActionResult, TargetType
from world.gm.constants import GMLevel

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext


@dataclass
class ApplyShadeUndeathAction(Action):
    """Make a character a Shade: the undead condition + its economy anchor.

    Grants the ``Undeath (Shade)`` condition and the ``undead-shade`` anchor
    distinction, which together stop natural anima regen, start the daily
    drain, and open essence feeding.
    """

    key: str = "gm_apply_shade"
    name: str = "Make Shade"
    icon: str = "ghost"
    category: str = "gm"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [MinimumGMLevelPrerequisite(GMLevel.JUNIOR)]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.species.factories import apply_shade_undeath  # noqa: PLC0415

        target_name = (kwargs.get("target_name") or "").strip()
        if not target_name:
            return ActionResult(success=False, message="Usage: makeshade <character>")
        target = actor.search(target_name, global_search=True)
        if target is None:
            return ActionResult(success=False, message=f"No character called '{target_name}'.")
        if target.character_sheet is None:
            return ActionResult(success=False, message="That is not a character.")
        apply_shade_undeath(target)
        return ActionResult(
            success=True,
            message=(
                f"{target.key} is a Shade now — the warmth will not come back on "
                "its own, and it leaks a little every day."
            ),
        )
