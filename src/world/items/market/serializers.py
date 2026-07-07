"""Market read serializers (#2066): the browse payloads.

Read-only — every mutation goes through the market actions, never REST
writes. The shop directory advertises services without remote execution
(the two-tier geography: you must visit the shop).
"""

from rest_framework import serializers

from world.items.market.models import (
    CraftingServiceOffer,
    MarketSquare,
    MarketStall,
    StockListing,
    WareListing,
)


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
        rows = [row for row in obj.stock_listings.all() if row.is_active]
        return StockListingSerializer(rows, many=True).data

    def get_ware_listings(self, obj: MarketStall) -> list[dict]:
        rows = [row for row in obj.ware_listings.all() if row.sold_at is None]
        return WareListingSerializer(rows, many=True).data


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
