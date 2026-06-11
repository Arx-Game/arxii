from django.contrib import admin

from world.currency.models import (
    CharacterPurse,
    CurrencyInstrumentDetails,
    CurrencyTransfer,
    OrganizationTreasury,
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
