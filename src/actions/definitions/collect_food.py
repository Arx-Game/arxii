"""CollectFoodAction — active food collection from a Field (#1864)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionContext, ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


@dataclass
class CollectFoodAction(Action):
    """Collect food from a Field's uncollected pool into the domain's stockpile.

    The single commit seam where telnet and web converge. Calls
    ``collect_field_food`` which zeroes the pool, rolls a Food Collection
    check, applies the band percentage, and lands food into the domain's
    ``FoodStockpile`` (capped at Granary capacity).

    kwargs:
        field_instance: RoomFeatureInstance — the Field to collect from.
    """

    key: str = "collect_food"
    name: str = "Collect Food"
    icon: str = "wheat"
    category: str = "agriculture"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.agriculture.services import collect_field_food  # noqa: PLC0415

        field_instance = kwargs.get("field_instance")
        if field_instance is None:
            return ActionResult(
                success=False,
                message="Which field? (collect food <field>)",
            )

        try:
            result = collect_field_food(actor, field_instance)
        except ValueError as exc:
            return ActionResult(success=False, message=str(exc))

        if result.catastrophe:
            return ActionResult(
                success=True,
                message=(
                    f"You gathered {result.gathered} food, but lost it all "
                    f"on the way back — catastrophe."
                ),
                data={
                    "gathered": result.gathered,
                    "landed": result.landed,
                    "overflow": result.overflow,
                    "catastrophe": True,
                },
            )

        msg = f"You collected {result.landed} food"
        if result.overflow > 0:
            msg += f" ({result.overflow} lost to overflow — granary full)"
        msg += "."

        return ActionResult(
            success=True,
            message=msg,
            data={
                "gathered": result.gathered,
                "landed": result.landed,
                "overflow": result.overflow,
                "catastrophe": False,
            },
        )
