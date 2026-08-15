"""Market read serializers (#2066): the browse payloads.

Read-only — every mutation goes through the market actions, never REST
writes. The shop directory advertises services without remote execution
(the two-tier geography: you must visit the shop).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rest_framework import serializers

from world.items.market.models import (
    CraftingServiceOffer,
    MarketSquare,
    MarketStall,
    StockListing,
    WareListing,
)

if TYPE_CHECKING:
    from world.scenes.models import Persona


def _viewer_persona(context: dict[str, Any]) -> Persona | None:
    """Active persona for the request account's own character, or None (#2995).

    Fail-closed (no request / not authenticated / no roster tenure all return
    None) — mirrors ``_active_persona_for_request`` in ``world.assets.views``.
    """
    from world.roster.models import RosterEntry  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    request = context.get("request")
    if request is None or not request.user.is_authenticated:
        return None
    entry = RosterEntry.objects.for_account(request.user).first()
    if entry is None:
        return None
    return active_persona_for_sheet(entry.character_sheet)


class StockListingSerializer(serializers.ModelSerializer):
    template_name = serializers.CharField(source="template.name", read_only=True)

    class Meta:
        model = StockListing
        fields = ["id", "template", "template_name", "price"]
        read_only_fields = fields


class WareListingSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="item_instance.display_name", read_only=True)
    seller_name = serializers.CharField(source="seller_persona.name", read_only=True)

    class Meta:
        model = WareListing
        fields = [
            "id",
            "item_instance",
            "item_name",
            "seller_name",
            "price",
            "open_style_slot",
            "open_facet_slot",
            "listed_at",
        ]
        read_only_fields = fields


class MarketStallSerializer(serializers.ModelSerializer):
    stock_listings = serializers.SerializerMethodField()
    ware_listings = serializers.SerializerMethodField()
    owner_name = serializers.SerializerMethodField()

    class Meta:
        model = MarketStall
        fields = ["id", "name", "owner_name", "stock_listings", "ware_listings"]
        read_only_fields = fields

    def get_owner_name(self, obj: MarketStall) -> str:
        return obj.owner_persona.name if obj.owner_persona_id else ""

    def get_stock_listings(self, obj: MarketStall) -> list[dict]:
        """Active stock, minus any reserved-stock rows the viewer's regard doesn't meet.

        Base price only (Decision 4 — no personalized price on browse); the
        regard-adjusted price is revealed at purchase-attempt time. Visibility =
        eligibility: same ``min_regard`` predicate the purchase-time gate checks.
        """
        from world.items.market.services import _shopkeeper_regard  # noqa: PLC0415

        rows = [row for row in obj.stock_listings.all() if row.is_active]
        if any(row.min_regard is not None for row in rows):
            viewer = _viewer_persona(self.context)
            regard = (
                _shopkeeper_regard(obj.shopkeeper_persona, viewer) if viewer is not None else None
            )
            rows = [
                row
                for row in rows
                if row.min_regard is None or (regard is not None and regard >= row.min_regard)
            ]
        return StockListingSerializer(rows, many=True, context=self.context).data

    def get_ware_listings(self, obj: MarketStall) -> list[dict]:
        rows = [row for row in obj.ware_listings.all() if row.sold_at is None]
        return WareListingSerializer(rows, many=True, context=self.context).data


class MarketSquareSerializer(serializers.ModelSerializer):
    stalls = MarketStallSerializer(many=True, read_only=True)

    class Meta:
        model = MarketSquare
        fields = ["id", "name", "realm", "stalls"]
        read_only_fields = fields


class ServiceOfferSerializer(serializers.ModelSerializer):
    """Shop-directory row: who crafts what, where — execution requires visiting."""

    crafter_name = serializers.CharField(source="crafter_persona.name", read_only=True)
    shop_room_id = serializers.IntegerField(source="shop_room.objectdb_id", read_only=True)

    class Meta:
        model = CraftingServiceOffer
        fields = ["id", "crafter_name", "recipe_kind", "fee", "shop_room_id"]
        read_only_fields = fields
