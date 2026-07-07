"""Market services (#2066): purchases, listings, finishing, service crafting.

All coin moves through ``currency.services.transfer`` (NPC sales are pure
sinks; PC-to-PC trades move coin without minting it). The description is the
buyer's — ``finish_ware`` writes player prose and stamps designer credit;
nothing here generates prose.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.items.market.models import (
    CraftingServiceOffer,
    FinishingPass,
    MarketSale,
    MarketStall,
    StockListing,
    WareListing,
)

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.currency.models import CharacterPurse
    from world.items.crafting.services import CraftRunResult
    from world.items.models import ItemInstance
    from world.scenes.models import Persona


class MarketServiceError(Exception):
    """A market refusal, carrying a player-safe message."""

    def __init__(self, message: str, *, user_message: str | None = None) -> None:
        super().__init__(message)
        self.user_message = user_message or message


def _purse(persona: Persona) -> CharacterPurse:
    from world.currency.services import get_or_create_purse  # noqa: PLC0415

    return get_or_create_purse(persona.character_sheet)


def _pay(buyer: Persona, seller: Persona | None, amount: int, reason: str) -> None:
    """Move coin: to the seller's purse, or a pure sink when seller is None."""
    from world.currency.services import transfer  # noqa: PLC0415

    if seller is not None:
        transfer(amount=amount, reason=reason, from_purse=_purse(buyer), to_purse=_purse(seller))
    else:
        transfer(amount=amount, reason=reason, from_purse=_purse(buyer))


def _host_cut(stall: MarketStall, price: int) -> int:
    """Route the host org's cut into its treasury; returns the cut amount."""
    if stall.host_org_id is None or stall.cut_percent <= 0:
        return 0
    return price * stall.cut_percent // 100


@transaction.atomic
def purchase_stock(*, listing: StockListing, buyer: Persona) -> ItemInstance:
    """Buy from an NPC stall: mint an instance of the template, sink the coin."""
    from world.items.models import ItemInstance  # noqa: PLC0415

    if not listing.is_active:
        msg = f"stock listing {listing.pk} inactive"
        raise MarketServiceError(msg, user_message="That stock is no longer sold.")
    _pay(buyer, None, listing.price, f"market stock: {listing.template.name}")
    instance = ItemInstance.objects.create(
        template=listing.template,
        holder_character_sheet=buyer.character_sheet,
    )
    MarketSale.objects.create(
        kind=MarketSale.SaleKind.STOCK,
        buyer_persona=buyer,
        item_instance=instance,
        price=listing.price,
    )
    return instance


@transaction.atomic
def list_ware(  # noqa: PLR0913 — keyword-only listing parameters
    *,
    stall: MarketStall,
    seller: Persona,
    item_instance: ItemInstance,
    price: int,
    open_style_slot: bool = True,
    open_facet_slot: bool = False,
) -> WareListing:
    """List an unfinished crafted instance for sale.

    Rules: the seller must hold the item and be credited as its crafter
    (the stall sells *your* work), and the ware must still be unfinished
    (no custom prose) — the finishing pass is the buyer's.
    """
    if item_instance.holder_character_sheet_id != seller.character_sheet_id:
        msg = "seller does not hold the instance"
        raise MarketServiceError(msg, user_message="You are not holding that item.")
    if item_instance.crafter_character_sheet_id != seller.character_sheet_id:
        msg = "seller is not the crafter"
        raise MarketServiceError(msg, user_message="Only your own craftwork can go on your stall.")
    if item_instance.custom_name or item_instance.custom_description:
        msg = "instance already finished"
        raise MarketServiceError(
            msg,
            user_message="That piece is already named and described — "
            "finished work is a gift or a commission, not stall stock.",
        )
    if stall.owner_persona_id is not None and stall.owner_persona_id != seller.pk:
        msg = "not the stall owner"
        raise MarketServiceError(msg, user_message="That stall is not yours.")
    return WareListing.objects.create(
        stall=stall,
        item_instance=item_instance,
        seller_persona=seller,
        price=price,
        open_style_slot=open_style_slot,
        open_facet_slot=open_facet_slot,
    )


@transaction.atomic
def purchase_ware(*, listing: WareListing, buyer: Persona) -> FinishingPass:
    """Buy an unfinished ware: transfer item + coin, mint the finishing pass."""
    from world.currency.services import transfer  # noqa: PLC0415

    if listing.sold_at is not None:
        msg = f"ware listing {listing.pk} already sold"
        raise MarketServiceError(msg, user_message="That piece has already sold.")
    if listing.seller_persona_id == buyer.pk:
        msg = "buying own listing"
        raise MarketServiceError(msg, user_message="It is already yours.")

    cut = _host_cut(listing.stall, listing.price)
    _pay(buyer, listing.seller_persona, listing.price - cut, "market ware sale")
    if cut:
        from world.currency.models import OrganizationTreasury  # noqa: PLC0415

        treasury, _ = OrganizationTreasury.objects.get_or_create(
            organization=listing.stall.host_org
        )
        transfer(
            amount=cut,
            reason=f"stall cut: {listing.stall.name}",
            from_purse=_purse(buyer),
            to_treasury=treasury,
        )

    instance = listing.item_instance
    instance.holder_character_sheet = buyer.character_sheet
    instance.save(update_fields=["holder_character_sheet"])

    listing.sold_at = timezone.now()
    listing.save(update_fields=["sold_at"])
    MarketSale.objects.create(
        kind=MarketSale.SaleKind.WARE,
        buyer_persona=buyer,
        seller_persona=listing.seller_persona,
        item_instance=instance,
        price=listing.price,
        host_cut=cut,
    )
    return FinishingPass.objects.create(listing=listing, buyer_persona=buyer)


@transaction.atomic
def finish_ware(
    *,
    finishing_pass: FinishingPass,
    actor: Persona,
    name: str,
    description: str,
) -> ItemInstance:
    """Consume the pass: the buyer names/describes the piece, taking designer credit.

    The prose is the player's own (design tenet — never generated). Open
    style/facet slots are exercised separately through the normal crafting
    actions; this pass covers identity.
    """
    if finishing_pass.buyer_persona_id != actor.pk:
        msg = "not the pass holder"
        raise MarketServiceError(msg, user_message="That finishing right is not yours.")
    if finishing_pass.consumed_at is not None:
        msg = "pass already consumed"
        raise MarketServiceError(msg, user_message="That piece is already finished.")
    if not name and not description:
        msg = "empty finishing"
        raise MarketServiceError(msg, user_message="Give the piece a name, a description, or both.")
    instance = finishing_pass.listing.item_instance
    if name:
        instance.custom_name = name
    if description:
        instance.custom_description = description
    instance.designer_character_sheet = actor.character_sheet
    instance.designer_persona_display = actor
    instance.save(
        update_fields=[
            "custom_name",
            "custom_description",
            "designer_character_sheet",
            "designer_persona_display",
        ]
    )
    finishing_pass.consumed_at = timezone.now()
    finishing_pass.save(update_fields=["consumed_at"])
    return instance


@transaction.atomic
def set_service_offer(
    *,
    crafter: Persona,
    recipe_kind: str,
    shop_room: object,
    fee: int,
    is_active: bool = True,
) -> CraftingServiceOffer:
    """Create/update the crafter's standing offer for a recipe kind at their shop."""
    offer, _created = CraftingServiceOffer.objects.update_or_create(
        crafter_persona=crafter,
        recipe_kind=recipe_kind,
        shop_room=shop_room,
        defaults={"fee": fee, "is_active": is_active},
    )
    return offer


@transaction.atomic
def run_service_craft(
    *,
    offer: CraftingServiceOffer,
    buyer: Persona,
    buyer_character: ObjectDB,
    item_instance: ItemInstance,
    target: object,
) -> CraftRunResult:
    """Run a crafting attempt with the OFFERING crafter's skill (#2066).

    Arx 1's loop made honest: the buyer must stand in the shop (crafting is
    station-anchored there), supplies the item and target, pays the fee up
    front (charged even on a failed roll — the smith worked either way);
    the crafter's character rolls the check and gets the crafter credit;
    the buyer takes designer credit. Works with the crafter offline.
    """
    from world.items.crafting.services import run_crafting_recipe  # noqa: PLC0415

    if not offer.is_active:
        msg = f"offer {offer.pk} inactive"
        raise MarketServiceError(msg, user_message="That service is not on offer.")
    location = buyer_character.location
    location_pk = location.pk if location is not None else None
    if location_pk != offer.shop_room.objectdb_id:
        msg = "buyer not at the shop"
        raise MarketServiceError(
            msg, user_message="You must be at the crafter's shop to use their service."
        )
    if item_instance.holder_character_sheet_id != buyer.character_sheet_id:
        msg = "buyer does not hold the instance"
        raise MarketServiceError(msg, user_message="You are not holding that item.")

    crafter_sheet = offer.crafter_persona.character_sheet
    crafter_character = crafter_sheet.character
    _pay(buyer, offer.crafter_persona, offer.fee, f"crafting service: {offer.recipe_kind}")

    result = run_crafting_recipe(
        kind=offer.recipe_kind,
        crafter_account=buyer_character.account,
        crafter_character=crafter_character,
        item_instance=item_instance,
        target=target,
    )
    item_instance.designer_character_sheet = buyer.character_sheet
    item_instance.designer_persona_display = buyer
    item_instance.save(update_fields=["designer_character_sheet", "designer_persona_display"])
    MarketSale.objects.create(
        kind=MarketSale.SaleKind.SERVICE,
        buyer_persona=buyer,
        seller_persona=offer.crafter_persona,
        item_instance=item_instance,
        price=offer.fee,
    )
    return result


def dual_provenance_line(instance: ItemInstance) -> str:
    """Render 'Crafted by X, Designed by Y' (collapsed when one person did both)."""
    crafter = instance.crafter_persona_display or (
        instance.crafter_character_sheet.primary_persona
        if instance.crafter_character_sheet_id
        else None
    )
    designer = instance.designer_persona_display or (
        instance.designer_character_sheet.primary_persona
        if instance.designer_character_sheet_id
        else None
    )
    if crafter is None and designer is None:
        return ""
    if designer is None or (crafter is not None and designer.pk == crafter.pk):
        return f"Crafted and Designed by {crafter.name}"
    if crafter is None:
        return f"Designed by {designer.name}"
    return f"Crafted by {crafter.name}, Designed by {designer.name}"
