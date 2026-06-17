"""Investigation actions (#1154) — searching a room for hidden clues."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.constants import ActionCategory
from actions.types import ActionResult, TargetType
from world.clues.constants import SEARCH_CHECK_TYPE_NAME

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext

# Placeholder cost magnitudes — tuned in a later author pass (#1143).
_SEARCH_AP_COST = 1
_SEARCH_FATIGUE_COST = 1


@dataclass
class SearchAction(Action):
    """Search the current room for hidden clues (#1154).

    The thin action wrapper over ``world.clues.services.search_room``: charges the
    declarative AP + mental-fatigue cost (base ``run()``), resolves the seeded Search
    CheckType, and reports what the searcher turns up. All player-visible result text is
    PLACEHOLDER — rewrite in voice before launch.
    """

    key: str = "search"
    name: str = "Search"
    icon: str = "magnifying-glass"
    category: str = "investigation"
    target_type: TargetType = TargetType.SELF

    ap_cost: int = _SEARCH_AP_COST
    fatigue_cost: int = _SEARCH_FATIGUE_COST
    fatigue_category: str = ActionCategory.MENTAL

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from evennia_extensions.models import RoomProfile  # noqa: PLC0415
        from world.checks.models import CheckType  # noqa: PLC0415
        from world.clues.services import search_room  # noqa: PLC0415

        room = actor.location
        if room is None:
            return ActionResult(success=False, message="PLACEHOLDER There's nowhere to search.")
        try:
            room_profile = room.room_profile
        except RoomProfile.DoesNotExist:
            return ActionResult(
                success=False, message="PLACEHOLDER There's nothing to search here."
            )
        try:
            search_check = CheckType.objects.get(name=SEARCH_CHECK_TYPE_NAME)
        except CheckType.DoesNotExist:
            return ActionResult(success=False, message="PLACEHOLDER You can't search right now.")

        found = search_room(actor, room_profile, search_check)
        if not found:
            return ActionResult(success=True, message="PLACEHOLDER You search but turn up nothing.")
        lines = ["PLACEHOLDER You uncover something:"]
        lines += [f"  {clue.name} — {clue.description}" for clue in found]
        return ActionResult(success=True, message="\n".join(lines))
