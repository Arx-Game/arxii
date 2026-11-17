"""The rite of settling action (#5124, replacing #4733's atone and decline actions).

``PerformSettlingRiteAction`` carries out every waiting reflection with one offering and one
roll. Telnet ``aura settle <offering>`` and the REST ``/api/magic/settling-rite/`` endpoint
converge here.

World imports are lazy inside ``execute()``: the action registry is imported very early and
the magic models pull in much of the world graph.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext

_NO_SHEET = "You have no aura to settle."
_NOT_CARRIED = "You are not carrying everything you offered."


@dataclass
class PerformSettlingRiteAction(Action):
    """Perform the rite of settling: one offering, one roll, every waiting reflection.

    kwargs:
        components_provided: ``ItemInstance`` rows the actor offers up; each must be held by
            the actor's own sheet.

    Refused, writing nothing, with no waiting reflection or no qualifying offering. The
    result lines are the actor's alone. A Sinner whose Sineater succumbed or fell at the rite is
    told privately once the rite has committed (``result.notices``, #5177).
    """

    key: str = "perform_settling_rite"
    name: str = "Settle your aura"
    icon: str = "sparkles"
    category: str = "magic"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        *,
        components_provided: list[Any] | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.items.models import ItemInstance  # noqa: PLC0415
        from world.magic.exceptions import (  # noqa: PLC0415
            DriftCorrectionError,
            RitualComponentError,
        )
        from world.magic.services.drift_correction import (  # noqa: PLC0415
            perform_settling_rite,
        )
        from world.magic.services.soul_tether import send_stored_notice  # noqa: PLC0415

        sheet = actor.character_sheet
        if sheet is None:
            return ActionResult(success=False, message=_NO_SHEET)
        components = components_provided if components_provided is not None else []
        # A generic dispatch can hand over raw ids or a non-list; only the actor's own items count.
        if not isinstance(components, list | tuple) or not all(
            isinstance(item, ItemInstance) and item.holder_character_sheet_id == sheet.pk
            for item in components
        ):
            return ActionResult(success=False, message=_NOT_CARRIED)
        components = list(components)
        try:
            result = perform_settling_rite(sheet, components=components)
        except (DriftCorrectionError, RitualComponentError) as exc:
            return ActionResult(success=False, message=exc.user_message)
        for notice in result.notices:
            send_stored_notice(notice.sheet, notice.line, ooc_note="Settling the Mire")
        message = "\n".join((f"{result.outcome_name}.", *result.lines))
        return ActionResult(success=True, message=message, data={"settling_rite_result": result})
