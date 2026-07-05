"""Crafting Actions: facet attach/detach, style attach (#1866).

Thin wrappers over ``world.items.services.crafting``/``world.items.services
.facets`` — the same service functions ``ItemFacetViewSet``/
``ItemStyleCraftViewSet`` call. No new business logic; domain exceptions
raised by the service layer are translated to failure ``ActionResult``s
(mirrors the ViewSets' own exception handling) rather than propagating.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from actions.base import Action
from actions.definitions.item_helpers import resolve_item_instance
from actions.prerequisites import HoldsItemPrerequisite, Prerequisite
from actions.types import ActionResult, TargetType
from world.items.exceptions import (
    CraftingCostUnaffordable,
    CraftingNotConfigured,
    CraftingStationBroken,
    CraftingStationRequired,
    FacetAlreadyAttached,
    FacetCapacityExceeded,
    StyleAlreadyAttached,
    StyleCapacityExceeded,
)
from world.items.services.crafting import craft_attach_facet, craft_attach_style
from world.items.services.facets import remove_facet_from_item

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext
    from world.items.models import ItemFacet
    from world.magic.models import Facet

_CRAFT_EXCEPTIONS = (
    FacetAlreadyAttached,
    FacetCapacityExceeded,
    StyleAlreadyAttached,
    StyleCapacityExceeded,
    CraftingNotConfigured,
    CraftingCostUnaffordable,
    CraftingStationRequired,
    CraftingStationBroken,
)


@dataclass
class AttachFacetAction(Action):
    """Roll the facet-attach crafting recipe and (on success) attach it."""

    key: str = "craft_attach_facet"
    name: str = "Attach Facet"
    icon: str = "gem"
    category: str = "items"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [HoldsItemPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        item_obj = kwargs.get("item")
        facet: Facet | None = kwargs.get("facet")
        if item_obj is None or facet is None:
            return ActionResult(success=False, message="Attach what facet, to what item?")
        instance = resolve_item_instance(item_obj)
        if instance is None:
            return ActionResult(success=False, message="That isn't an item.")
        try:
            result = craft_attach_facet(
                crafter_account=cast("AccountDB", actor.account),
                crafter_character=actor,
                item_instance=instance,
                facet=facet,
            )
        except _CRAFT_EXCEPTIONS as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(success=True, data={"result": result})


@dataclass
class DetachFacetAction(Action):
    """Detach an already-attached facet from an item."""

    key: str = "craft_detach_facet"
    name: str = "Detach Facet"
    icon: str = "gem-off"
    category: str = "items"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [HoldsItemPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        item_facet: ItemFacet | None = kwargs.get("item_facet")
        if item_facet is None:
            return ActionResult(success=False, message="Detach which facet?")
        remove_facet_from_item(item_facet=item_facet)
        return ActionResult(success=True)


@dataclass
class AttachStyleAction(Action):
    """Roll the style-attach crafting recipe and (on success) attach it.

    Permanent by design — no ``DetachStyleAction`` exists; the underlying
    ``remove_style_from_item`` service doesn't exist anywhere, on the web or
    otherwise (verified during spec — see #1866's anti-reinvention ledger).
    """

    key: str = "craft_attach_style"
    name: str = "Attach Style"
    icon: str = "brush"
    category: str = "items"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [HoldsItemPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        item_obj = kwargs.get("item")
        style = kwargs.get("style")
        if item_obj is None or style is None:
            return ActionResult(success=False, message="Attach what style, to what item?")
        instance = resolve_item_instance(item_obj)
        if instance is None:
            return ActionResult(success=False, message="That isn't an item.")
        try:
            result = craft_attach_style(
                crafter_account=cast("AccountDB", actor.account),
                crafter_character=actor,
                item_instance=instance,
                style=style,
            )
        except _CRAFT_EXCEPTIONS as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(success=True, data={"result": result})
