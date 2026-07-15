"""Market actions (#2066) — the buy/list/finish/service seam.

Thin REGISTRY wrappers over ``world.items.market.services``; shared by the
web market center dispatch and the telnet ``market`` namespace. Browsing is
REST (read-only); every mutation converges here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from evennia.objects.models import ObjectDB

from actions.base import Action
from actions.constants import ActionCategory
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from actions.types import ActionContext

_MSG_NO_PERSONA = "You have no active character."


def _active_persona(actor: ObjectDB):
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    sheet = actor.character_sheet
    if sheet is None:
        return None
    return active_persona_for_sheet(sheet)


@dataclass
class _MarketAction(Action):
    """Shared shape for market verbs."""

    category: str = "items"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF


@dataclass
class BuyStockAction(_MarketAction):
    """Buy NPC stall stock (materials/reagents/necessities). Kwargs: ``listing_id``."""

    key: str = "market_buy_stock"
    name: str = "Buy Stock"
    icon: str = "shopping-basket"

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from django.core.exceptions import ValidationError  # noqa: PLC0415

        from world.items.market.models import StockListing  # noqa: PLC0415
        from world.items.market.services import (  # noqa: PLC0415
            MarketServiceError,
            purchase_stock,
        )

        persona = _active_persona(actor)
        if persona is None:
            return ActionResult(success=False, message=_MSG_NO_PERSONA)
        listing = StockListing.objects.filter(pk=kwargs.get("listing_id")).first()
        if listing is None:
            return ActionResult(success=False, message="No such stock listing.")
        try:
            instance = purchase_stock(listing=listing, buyer=persona)
        except MarketServiceError as exc:
            return ActionResult(success=False, message=exc.user_message)
        except ValidationError as exc:
            return ActionResult(success=False, message=exc.messages[0])
        return ActionResult(
            success=True,
            message=f"You buy {instance.display_name} for {listing.price} coppers.",
            data={"item_instance_id": instance.pk},
        )


@dataclass
class BuyWareAction(_MarketAction):
    """Buy an unfinished PC ware. Kwargs: ``listing_id``."""

    key: str = "market_buy_ware"
    name: str = "Buy Ware"
    icon: str = "shopping-bag"

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from django.core.exceptions import ValidationError  # noqa: PLC0415

        from world.items.market.models import WareListing  # noqa: PLC0415
        from world.items.market.services import (  # noqa: PLC0415
            MarketServiceError,
            purchase_ware,
        )

        persona = _active_persona(actor)
        if persona is None:
            return ActionResult(success=False, message=_MSG_NO_PERSONA)
        listing = WareListing.objects.filter(pk=kwargs.get("listing_id")).first()
        if listing is None:
            return ActionResult(success=False, message="No such ware listing.")
        try:
            finishing_pass = purchase_ware(listing=listing, buyer=persona)
        except MarketServiceError as exc:
            return ActionResult(success=False, message=exc.user_message)
        except ValidationError as exc:
            return ActionResult(success=False, message=exc.messages[0])
        return ActionResult(
            success=True,
            message=(
                f"You buy {listing.item_instance.display_name} for {listing.price} "
                "coppers. It is yours to name and describe — finish it with "
                f"'market/finish {finishing_pass.pk}'."
            ),
            data={"finishing_pass_id": finishing_pass.pk},
        )


@dataclass
class ListWareAction(_MarketAction):
    """List your unfinished craftwork on a stall.

    Kwargs: ``stall_id``, ``item_instance_id``, ``price``, optional
    ``open_style_slot``/``open_facet_slot``.
    """

    key: str = "market_list_ware"
    name: str = "List Ware"
    icon: str = "tag"

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.items.market.models import MarketStall  # noqa: PLC0415
        from world.items.market.services import (  # noqa: PLC0415
            MarketServiceError,
            list_ware,
        )
        from world.items.models import ItemInstance  # noqa: PLC0415

        persona = _active_persona(actor)
        if persona is None:
            return ActionResult(success=False, message=_MSG_NO_PERSONA)
        stall = MarketStall.objects.filter(pk=kwargs.get("stall_id")).first()
        instance = ItemInstance.objects.filter(pk=kwargs.get("item_instance_id")).first()
        price = kwargs.get("price")
        if stall is None or instance is None or not price:
            return ActionResult(success=False, message="Give a stall, an item, and a price.")
        try:
            listing = list_ware(
                stall=stall,
                seller=persona,
                item_instance=instance,
                price=int(price),
                open_style_slot=bool(kwargs.get("open_style_slot", True)),
                open_facet_slot=bool(kwargs.get("open_facet_slot", False)),
            )
        except MarketServiceError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=f"{instance.display_name} listed at {listing.price} coppers.",
            data={"listing_id": listing.pk},
        )


@dataclass
class FinishWareAction(_MarketAction):
    """Finish a purchased ware: your name, your prose. Kwargs: ``finishing_pass_id``,
    ``item_name``, ``description``."""

    key: str = "market_finish_ware"
    name: str = "Finish Ware"
    icon: str = "feather"

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.items.market.models import FinishingPass  # noqa: PLC0415
        from world.items.market.services import (  # noqa: PLC0415
            MarketServiceError,
            dual_provenance_line,
            finish_ware,
        )

        persona = _active_persona(actor)
        if persona is None:
            return ActionResult(success=False, message=_MSG_NO_PERSONA)
        finishing_pass = FinishingPass.objects.filter(pk=kwargs.get("finishing_pass_id")).first()
        if finishing_pass is None:
            return ActionResult(success=False, message="No such finishing right.")
        try:
            instance = finish_ware(
                finishing_pass=finishing_pass,
                actor=persona,
                name=(kwargs.get("item_name") or "").strip(),
                description=(kwargs.get("description") or "").strip(),
            )
        except MarketServiceError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=f"{instance.display_name} is finished. {dual_provenance_line(instance)}.",
        )


@dataclass
class SetServiceOfferAction(_MarketAction):
    """Set your standing craft-as-service offer at your current shop room.

    Kwargs: ``recipe_kind``, ``fee``, optional ``active`` (default true).
    """

    key: str = "market_set_service_offer"
    name: str = "Offer Crafting Service"
    icon: str = "hammer"

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from evennia_extensions.models import RoomProfile  # noqa: PLC0415
        from world.items.market.services import set_service_offer  # noqa: PLC0415

        persona = _active_persona(actor)
        if persona is None:
            return ActionResult(success=False, message=_MSG_NO_PERSONA)
        location = actor.location
        profile = RoomProfile.objects.filter(objectdb=location).first() if location else None
        if profile is None:
            return ActionResult(success=False, message="You're not in a room.")
        recipe_kind = (kwargs.get("recipe_kind") or "").strip()
        fee = kwargs.get("fee")
        if not recipe_kind or fee is None:
            return ActionResult(success=False, message="Give a recipe kind and a fee.")
        offer = set_service_offer(
            crafter=persona,
            recipe_kind=recipe_kind,
            shop_room=profile,
            fee=int(fee),
            is_active=bool(kwargs.get("active", True)),
        )
        state = "open" if offer.is_active else "closed"
        return ActionResult(
            success=True,
            message=f"Your {offer.recipe_kind} service here is {state} at {offer.fee} coppers.",
        )


@dataclass
class ServiceCraftAction(_MarketAction):
    """Craft using a crafter's standing offer, at their shop.

    Kwargs: ``offer_id``, ``item_instance_id``, ``target_id`` (facet or style
    pk per the offer's recipe kind).
    """

    key: str = "market_service_craft"
    name: str = "Commission Crafting"
    icon: str = "anvil"

    def execute(  # noqa: PLR0911 — one return per refusal reason
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from django.core.exceptions import ValidationError  # noqa: PLC0415

        from world.items.market.models import CraftingServiceOffer  # noqa: PLC0415
        from world.items.market.services import (  # noqa: PLC0415
            MarketServiceError,
            run_service_craft,
        )
        from world.items.models import ItemInstance  # noqa: PLC0415

        persona = _active_persona(actor)
        if persona is None:
            return ActionResult(success=False, message=_MSG_NO_PERSONA)
        offer = CraftingServiceOffer.objects.filter(pk=kwargs.get("offer_id")).first()
        instance = ItemInstance.objects.filter(pk=kwargs.get("item_instance_id")).first()
        if offer is None or instance is None:
            return ActionResult(success=False, message="Give a service offer and an item.")
        target = _resolve_craft_target(offer.recipe_kind, kwargs.get("target_id"))
        if target is None:
            return ActionResult(success=False, message="No such facet or style.")
        try:
            result = run_service_craft(
                offer=offer,
                buyer=persona,
                buyer_character=actor,
                item_instance=instance,
                target=target,
            )
        except MarketServiceError as exc:
            return ActionResult(success=False, message=exc.user_message)
        except ValidationError as exc:
            return ActionResult(success=False, message="; ".join(exc.messages))
        if not result.attached:
            suffix = f" — {result.consequence_label}." if result.consequence_label else "."
            return ActionResult(success=False, message=f"The attempt fails{suffix}")
        tier = f" ({result.quality_tier})" if result.quality_tier else ""
        return ActionResult(success=True, message=f"The work is done{tier}.")


def _resolve_craft_target(recipe_kind: str, target_id: object) -> object | None:
    """Resolve the facet/style target for a service-craft attempt."""
    from world.items.crafting.constants import CraftingRecipeKind  # noqa: PLC0415

    if recipe_kind == CraftingRecipeKind.FACET_ATTACH:
        from world.magic.models import Facet  # noqa: PLC0415

        return Facet.objects.filter(pk=target_id).first()
    if recipe_kind == CraftingRecipeKind.STYLE_ATTACH:
        from world.items.models import Style  # noqa: PLC0415

        return Style.objects.filter(pk=target_id).first()
    return None
