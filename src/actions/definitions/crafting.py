"""Crafting Actions: facet attach/detach, style attach (#1866).

Thin wrappers over ``world.items.services.crafting``/``world.items.services
.facets`` — the same service functions ``ItemFacetViewSet``/
``ItemStyleCraftViewSet`` call. Operate directly on ``ItemInstance``
(never a physical ``ObjectDB``) — crafting's ownership model is
body/tenure-keyed (``OwnsItemInstancePrerequisite``), matching
``_user_holds_item`` in ``world/items/views.py``, not physical possession.
Domain exceptions raised by the service layer are translated to failure
``ActionResult``s (mirrors the ViewSets' own exception handling) rather
than propagating.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.prerequisites import (
    HasCharacterSheetPrerequisite,
    OwnsItemInstancePrerequisite,
    Prerequisite,
)
from actions.types import ActionResult, TargetType
from world.items.exceptions import (
    CraftingCostUnaffordable,
    CraftingNotConfigured,
    CraftingStationBroken,
    CraftingStationRequired,
    FacetAlreadyAttached,
    FacetCapacityExceeded,
    ItemError,
    StyleAlreadyAttached,
    StyleCapacityExceeded,
)
from world.items.services.crafting import craft_attach_facet, craft_attach_style, craft_create_item
from world.items.services.facets import remove_facet_from_item
from world.roster.selectors import get_account_for_character

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext
    from world.items.models import ItemFacet, ItemInstance, ItemTemplate
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
    ItemError,
)

_NO_ACCOUNT_MSG = "No account plays this character."


@dataclass
class AttachFacetAction(Action):
    """Roll the facet-attach crafting recipe and (on success) attach it."""

    key: str = "craft_attach_facet"
    name: str = "Attach Facet"
    icon: str = "gem"
    category: str = "items"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [OwnsItemInstancePrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        item_instance: ItemInstance | None = kwargs.get("item_instance")
        facet: Facet | None = kwargs.get("facet")
        if item_instance is None or facet is None:
            return ActionResult(success=False, message="Attach what facet, to what item?")
        crafter_account = get_account_for_character(actor)
        if crafter_account is None:
            return ActionResult(success=False, message=_NO_ACCOUNT_MSG)
        try:
            result = craft_attach_facet(
                crafter_account=crafter_account,
                crafter_character=actor,
                item_instance=item_instance,
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
        return [OwnsItemInstancePrerequisite()]

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
        return [OwnsItemInstancePrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        item_instance: ItemInstance | None = kwargs.get("item_instance")
        style = kwargs.get("style")
        if item_instance is None or style is None:
            return ActionResult(success=False, message="Attach what style, to what item?")
        crafter_account = get_account_for_character(actor)
        if crafter_account is None:
            return ActionResult(success=False, message=_NO_ACCOUNT_MSG)
        try:
            result = craft_attach_style(
                crafter_account=crafter_account,
                crafter_character=actor,
                item_instance=item_instance,
                style=style,
            )
        except _CRAFT_EXCEPTIONS as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(success=True, data={"result": result})


@dataclass
class CreateItemAction(Action):
    """Roll the ITEM_CREATE recipe and (on success) mint a new ItemInstance.

    The player may supply a custom name and description for the created item
    (mirrors the market's ``finish_ware`` pattern — player prose, not generated).
    No ``OwnsItemInstancePrerequisite`` — there is no pre-existing item to own.
    """

    key: str = "craft_create_item"
    name: str = "Create Item"
    icon: str = "hammer"
    category: str = "items"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [HasCharacterSheetPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        output_template: ItemTemplate | None = kwargs.get("output_template")
        if output_template is None:
            return ActionResult(success=False, message="Create what?")
        custom_name = kwargs.get("custom_name", "")
        custom_description = kwargs.get("custom_description", "")
        accent_targets = kwargs.get("accent_targets") or []
        crafter_account = get_account_for_character(actor)
        if crafter_account is None:
            return ActionResult(success=False, message=_NO_ACCOUNT_MSG)
        try:
            result = craft_create_item(
                crafter_account=crafter_account,
                crafter_character=actor,
                output_template=output_template,
                custom_name=custom_name,
                custom_description=custom_description,
                accent_targets=accent_targets,
            )
        except _CRAFT_EXCEPTIONS as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(success=True, data={"result": result})


@dataclass
class RemoveAccentAction(Action):
    """Strip one worked-in Accent off an owned piece (#2886). No refund."""

    key: str = "craft_remove_accent"
    name: str = "Remove Accent"
    icon: str = "eraser"
    category: str = "items"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [OwnsItemInstancePrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.items.services.recycle import remove_item_accent  # noqa: PLC0415

        item_instance: ItemInstance | None = kwargs.get("item_instance")
        target = kwargs.get("accent_target")
        if item_instance is None or target is None:
            return ActionResult(success=False, message="Remove which accent, from what?")
        try:
            remove_item_accent(
                item_instance=item_instance,
                target=target,
                actor_sheet=item_instance.holder_character_sheet,
            )
        except _CRAFT_EXCEPTIONS as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(success=True, data={})


@dataclass
class RecycleItemAction(Action):
    """Destroy an owned piece for a fraction of its materials (#2886).

    Story-protected items (legend attached) need a GM-approved RecycleRequest
    first — the action surfaces that as its failure message.
    """

    key: str = "recycle_item"
    name: str = "Recycle Item"
    icon: str = "recycle"
    category: str = "items"
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [OwnsItemInstancePrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.items.services.recycle import recycle_item  # noqa: PLC0415

        item_instance: ItemInstance | None = kwargs.get("item_instance")
        if item_instance is None:
            return ActionResult(success=False, message="Recycle what?")
        try:
            result = recycle_item(
                item_instance=item_instance,
                actor_sheet=item_instance.holder_character_sheet,
            )
        except _CRAFT_EXCEPTIONS as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(success=True, data={"salvaged": list(result.salvaged)})
