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
        """Active stock, minus whatever the viewer's regard doesn't clear.

        Base price only (Decision 4 — no personalized price on browse); the
        regard-adjusted price is revealed at purchase-attempt time. Visibility
        = eligibility: for a resolvable viewer this is the EXACT same
        ``_regard_gate_passes`` predicate the purchase-time gate checks —
        refusal floor included, not just an authored ``min_regard`` — so a
        hard-refused buyer never sees a listing they'd bounce off at
        purchase. An unresolvable viewer (no roster tenure / anonymous) can't
        have their regard evaluated at all, so only authored ``min_regard``
        rows are hidden as a conservative default; the floor never applies
        without a real persona to check it against.
        """
        rows = [row for row in obj.stock_listings.all() if row.is_active]
        if obj.shopkeeper_persona_id is not None:
            from world.items.market.services import _regard_gate_passes  # noqa: PLC0415

            viewer = _viewer_persona(self.context)
            if viewer is None:
                rows = [row for row in rows if row.min_regard is None]
            else:
                rows = [
                    row
                    for row in rows
                    if _regard_gate_passes(obj.shopkeeper_persona, viewer, row.min_regard)
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
