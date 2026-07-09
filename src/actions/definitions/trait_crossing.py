"""Action for resolving a pending TRAIT thread crossing offer (#1989)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from actions.base import Action
from actions.types import ActionResult, TargetType


@dataclass
class ResolveTraitCrossingOfferAction(Action):
    """Resolve a pending trait crossing offer by picking an option.

    Shared action.run() seam — telnet (CmdTraitCrossing) and web
    (TraitCrossingRespondView) converge here.
    """

    key: str = "resolve_trait_crossing"
    name: str = "Choose Trait Crossing"
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
            TraitCrossingOfferNotFoundError,
            TraitCrossingOfferStaleError,
        )
        from world.magic.services.trait_crossing import (  # noqa: PLC0415
            resolve_trait_crossing_offer,
        )

        try:
            result = resolve_trait_crossing_offer(offer, option=option)
        except TraitCrossingOfferNotFoundError:
            return ActionResult(
                success=False,
                message="You have no pending trait crossing offer.",
            )
        except TraitCrossingOfferStaleError:
            return ActionResult(
                success=False,
                message="That option is no longer available for this crossing.",
            )
        return ActionResult(
            success=True,
            message=f"Your {result.option_name} takes hold.",
            data={"trait_crossing_result": result},
        )


# Module-level singleton
resolve_trait_crossing = ResolveTraitCrossingOfferAction()
