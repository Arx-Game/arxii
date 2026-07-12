"""CollectFoodAction — active food collection from a Field (#1864)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionContext, ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.room_features.models import RoomFeatureInstance


def _resolve_field_instance(actor: ObjectDB, field_instance_id: Any) -> RoomFeatureInstance | None:
    """Resolve the Field ``RoomFeatureInstance`` to collect from.

    Web dispatch passes ``field_instance_id`` (a pk); telnet stands in the room
    and we resolve that room's active FIELD feature. The REST dispatch path does
    no ObjectDB/instance resolution (see ``actions/CLAUDE.md``), so we resolve
    here — the same ``execute()`` works for a telnet ``.run()`` passing a
    pre-resolved ``field_instance`` and a REST call passing a raw id.
    """
    from world.room_features.constants import RoomFeatureServiceStrategy  # noqa: PLC0415
    from world.room_features.models import RoomFeatureInstance  # noqa: PLC0415

    fields = RoomFeatureInstance.objects.active().filter(
        feature_kind__service_strategy=RoomFeatureServiceStrategy.FIELD
    )
    if field_instance_id is not None:
        return fields.filter(pk=field_instance_id).first()

    location = getattr(actor, "location", None)  # noqa: GETATTR_LITERAL
    if location is None:
        return None
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415

    room_profile = RoomProfile.objects.filter(objectdb=location).first()
    if room_profile is None:
        return None
    return fields.filter(room_profile=room_profile).first()


@dataclass
class CollectFoodAction(Action):
    """Collect food from a Field's uncollected pool into the domain's stockpile.

    The single commit seam where telnet and web converge. Calls
    ``collect_field_food`` which zeroes the pool, rolls a Food Collection
    check, applies the band percentage, and lands food into the domain's
    ``FoodStockpile`` (capped at Granary capacity).

    kwargs (resolved in priority order):
        field_instance: RoomFeatureInstance — a pre-resolved Field (telnet ``.run()``).
        field_instance_id: int — a Field feature pk (web/REST dispatch).
        (neither) — the active FIELD feature in ``actor.location`` (telnet ``harvest``).
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
            field_instance = _resolve_field_instance(actor, kwargs.get("field_instance_id"))
        if field_instance is None:
            return ActionResult(
                success=False,
                message="There's no field here to collect from.",
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
