"""Admin for player<->player negotiated trade (#2990).

Staff-visibility only — every mutation a player makes goes through the trade
actions, never admin writes. Read-only fields cover the state machine so
staff can inspect a stuck negotiation without hand-editing it into an
inconsistent state (e.g. COMPLETED with unmoved stakes).
"""

from django.contrib import admin

from world.items.trade.models import TradeItemStake, TradeSession


class TradeItemStakeInline(admin.TabularInline):
    model = TradeItemStake
    extra = 0
    fields = ["item_instance", "offered_by_sheet", "staked_at"]
    readonly_fields = ["staked_at"]
    raw_id_fields = ["item_instance", "offered_by_sheet"]


@admin.register(TradeSession)
class TradeSessionAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "initiator_sheet",
        "counterparty_sheet",
        "status",
        "initiator_confirmed",
        "counterparty_confirmed",
        "created_at",
    ]
    list_filter = ["status"]
    raw_id_fields = ["initiator_sheet", "counterparty_sheet"]
    readonly_fields = [
        "status",
        "initiator_confirmed",
        "counterparty_confirmed",
        "initiator_coppers",
        "counterparty_coppers",
        "created_at",
        "resolved_at",
    ]
    inlines = [TradeItemStakeInline]

    def has_add_permission(self, request, obj=None) -> bool:  # noqa: ARG002
        return False
