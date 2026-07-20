from django.contrib import admin

from world.currency.models import (
    CharacterPurse,
    CurrencyInstrumentDetails,
    CurrencyTransfer,
    DistinctionPurseDrain,
    FavorTokenDetails,
    OrganizationTreasury,
    PurseDrainWeek,
)


@admin.register(CharacterPurse)
class CharacterPurseAdmin(admin.ModelAdmin):
    list_display = ("character_sheet", "balance")
    search_fields = ("character_sheet__character__db_key",)
    raw_id_fields = ("character_sheet",)


@admin.register(OrganizationTreasury)
class OrganizationTreasuryAdmin(admin.ModelAdmin):
    list_display = ("organization", "balance", "spend_rank_max")
    search_fields = ("organization__name",)
    raw_id_fields = ("organization",)


@admin.register(CurrencyTransfer)
class CurrencyTransferAdmin(admin.ModelAdmin):
    list_display = (
        "amount",
        "reason",
        "from_purse",
        "from_treasury",
        "to_purse",
        "to_treasury",
        "created_at",
    )
    list_filter = ("created_at",)
    search_fields = ("reason",)
    raw_id_fields = ("from_purse", "from_treasury", "to_purse", "to_treasury")
    date_hierarchy = "created_at"


@admin.register(CurrencyInstrumentDetails)
class CurrencyInstrumentDetailsAdmin(admin.ModelAdmin):
    list_display = ("denomination", "face_value", "item_instance")
    list_filter = ("denomination",)
    raw_id_fields = ("item_instance",)


@admin.register(FavorTokenDetails)
class FavorTokenDetailsAdmin(admin.ModelAdmin):
    list_display = (
        "issuing_organization",
        "provenance_note",
        "minted_at",
        "redeemed_at",
        "item_instance",
    )
    list_filter = ("issuing_organization",)
    search_fields = ("provenance_note", "issuing_organization__name")
    raw_id_fields = ("item_instance", "issuing_organization")
    date_hierarchy = "minted_at"


@admin.register(DistinctionPurseDrain)
class DistinctionPurseDrainAdmin(admin.ModelAdmin):
    list_display = ("distinction", "drain_percent", "floor_coppers")
    search_fields = ("distinction__name",)
    raw_id_fields = ("distinction",)


@admin.register(PurseDrainWeek)
class PurseDrainWeekAdmin(admin.ModelAdmin):
    list_display = (
        "character_sheet",
        "game_week",
        "opening_balance",
        "outflows",
        "amount_drained",
        "drained_at",
    )
    list_filter = ("game_week",)
    search_fields = ("character_sheet__character__db_key",)
    raw_id_fields = ("character_sheet", "game_week")
    date_hierarchy = "snapshot_at"
