"""Action for resolving a pending thread crossing offer (generalized, #1990)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from actions.base import Action
from actions.types import ActionResult, TargetType


@dataclass
class ResolveCrossingOfferAction(Action):
    """Resolve a pending crossing offer by picking an option.

    Shared action.run() seam — telnet (CmdThreads) and web
    (CrossingRespondView) converge here.
    """

    key: str = "resolve_crossing_offer"
    name: str = "Choose Crossing"
    icon: str = "sparkles"
    category: str = "magic"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: Any,
        context: Any = None,
        *,
        offer: Any,
        option: Any,
        **kwargs: Any,
    ) -> ActionResult:
        from world.magic.exceptions import (  # noqa: PLC0415
            CrossingOfferNotFoundError,
            CrossingOfferStaleError,
        )
        from world.magic.services.crossing import (  # noqa: PLC0415
            resolve_crossing_offer,
        )

        try:
            result = resolve_crossing_offer(offer, option=option)
        except CrossingOfferNotFoundError:
            return ActionResult(
                success=False,
                message="You have no pending crossing offer.",
            )
        except CrossingOfferStaleError:
            return ActionResult(
                success=False,
                message="That option is no longer available for this crossing.",
            )
        return ActionResult(
            success=True,
            message=f"Your {result.option_name} takes hold.",
            data={"crossing_result": result},
        )


# Module-level singleton
resolve_crossing_offer = ResolveCrossingOfferAction()
