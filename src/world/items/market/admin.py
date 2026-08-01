"""Admin for the market square (#2862 gap close).

The market app shipped with no admin at all — which became load-bearing when
#2862 made ``MarketStall.stall_kind`` the thing that turns a stall into a
fence. Without this, the only fence in the world is wherever the demo seed
dropped one, and staff cannot place one in a crime neighborhood.
"""

from django.contrib import admin

from world.items.market.models import (
    CraftingServiceOffer,
    MarketSale,
    MarketSquare,
    MarketStall,
    StockListing,
    WareListing,
)


class StockListingInline(admin.TabularInline):
    model = StockListing
    extra = 0
    raw_id_fields = ["template"]


class MarketStallInline(admin.TabularInline):
    model = MarketStall
    extra = 0
    fields = ["name", "stall_kind", "owner_persona", "host_org", "cut_percent"]
    raw_id_fields = ["owner_persona", "host_org"]


@admin.register(MarketSquare)
class MarketSquareAdmin(admin.ModelAdmin):
    list_display = ["name", "area", "realm"]
    search_fields = ["name"]
    raw_id_fields = ["area", "realm"]
    inlines = [MarketStallInline]


@admin.register(MarketStall)
class MarketStallAdmin(admin.ModelAdmin):
    """Where a fence gets placed — ``stall_kind`` is the whole point (#2862)."""

    list_display = ["name", "stall_kind", "square", "owner_persona", "host_org"]
    list_filter = ["stall_kind"]
    search_fields = ["name", "square__name"]
    raw_id_fields = ["square", "owner_persona", "host_org"]
    inlines = [StockListingInline]


@admin.register(WareListing)
class WareListingAdmin(admin.ModelAdmin):
    list_display = ["item_instance", "stall", "seller_persona", "price", "sold_at"]
    raw_id_fields = ["stall", "item_instance", "seller_persona"]


@admin.register(CraftingServiceOffer)
class CraftingServiceOfferAdmin(admin.ModelAdmin):
    list_display = ["crafter_persona", "recipe_kind", "shop_room", "fee", "is_active"]
    list_filter = ["is_active"]
    raw_id_fields = ["crafter_persona", "shop_room"]


@admin.register(MarketSale)
class MarketSaleAdmin(admin.ModelAdmin):
    """Read-only ledger — sales are history, never fabricated in admin."""

    list_display = ["kind", "buyer_persona", "seller_persona", "price", "occurred_at"]
    list_filter = ["kind"]
    raw_id_fields = ["buyer_persona", "seller_persona", "item_instance"]
    readonly_fields = [
        "kind",
        "buyer_persona",
        "seller_persona",
        "item_instance",
        "price",
        "host_cut",
        "occurred_at",
    ]

    def has_add_permission(self, request, obj=None) -> bool:  # noqa: ARG002
        return False

    def has_change_permission(self, request, obj=None) -> bool:  # noqa: ARG002
        return False
