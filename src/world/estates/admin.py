from django.contrib import admin

from world.estates.models import (
    Bequest,
    EstateClaim,
    EstateConfig,
    EstateSettlement,
    Will,
    WillExecutor,
)


class WillExecutorInline(admin.TabularInline):
    model = WillExecutor
    extra = 0
    raw_id_fields = ("persona",)


class BequestInline(admin.TabularInline):
    model = Bequest
    extra = 0
    raw_id_fields = ("item", "building", "business", "recipient_persona", "recipient_organization")


@admin.register(Will)
class WillAdmin(admin.ModelAdmin):
    list_display = ("character_sheet", "updated_at")
    raw_id_fields = ("character_sheet",)
    inlines = (WillExecutorInline, BequestInline)


class EstateClaimInline(admin.TabularInline):
    model = EstateClaim
    extra = 0
    raw_id_fields = ("item", "claimant_persona", "claimant_organization")


@admin.register(EstateSettlement)
class EstateSettlementAdmin(admin.ModelAdmin):
    list_display = ("character_sheet", "status", "settled_via", "opened_at", "deadline")
    list_filter = ("status", "settled_via")
    raw_id_fields = ("character_sheet",)
    inlines = (EstateClaimInline,)


@admin.register(EstateConfig)
class EstateConfigAdmin(admin.ModelAdmin):
    list_display = ("pk", "settlement_window_days")
