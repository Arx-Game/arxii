"""
Admin interface for progression rewards models.
"""

from django.contrib import admin

from world.progression.models import (
    CharacterXP,
    CharacterXPTransaction,
    DevelopmentPoints,
    DevelopmentTransaction,
    ExperiencePointsData,
    XPTransaction,
)


@admin.register(ExperiencePointsData)
class ExperiencePointsDataAdmin(admin.ModelAdmin):
    """Admin interface for ExperiencePointsData."""

    autocomplete_fields = ["account"]

    list_display = ["account", "current_available", "total_earned", "total_spent"]
    list_filter = ["updated_date"]
    search_fields = ["account__username"]
    readonly_fields = ["created_date", "updated_date", "current_available"]

    def current_available(self, obj):
        return obj.current_available

    current_available.short_description = "Available XP"


@admin.register(XPTransaction)
class XPTransactionAdmin(admin.ModelAdmin):
    """Admin interface for XPTransaction."""

    autocomplete_fields = ["account", "character", "gm"]

    list_display = ["account", "amount", "reason", "description", "transaction_date"]
    list_filter = ["reason", "transaction_date"]
    search_fields = ["account__username", "description"]
    readonly_fields = ["transaction_date"]


@admin.register(DevelopmentPoints)
class DevelopmentPointsAdmin(admin.ModelAdmin):
    """Admin interface for DevelopmentPoints."""

    autocomplete_fields = ["character_sheet"]

    list_display = ["character_sheet", "trait", "total_earned"]
    list_filter = ["trait__trait_type", "updated_date"]
    search_fields = ["character_sheet__character__db_key", "trait__name"]
    readonly_fields = ["created_date", "updated_date"]


@admin.register(DevelopmentTransaction)
class DevelopmentTransactionAdmin(admin.ModelAdmin):
    """Admin interface for DevelopmentTransaction."""

    autocomplete_fields = ["character_sheet", "gm", "scene"]

    list_display = [
        "character_sheet",
        "trait",
        "source",
        "amount",
        "reason",
        "transaction_date",
    ]
    list_filter = ["source", "reason", "transaction_date"]
    search_fields = ["character_sheet__character__db_key", "trait__name", "description"]
    readonly_fields = ["transaction_date"]


@admin.register(CharacterXP)
class CharacterXPAdmin(admin.ModelAdmin):
    """The per-character XP ledger (#3748): what was earned on and spent on a character.

    Read-only counters — these are maintained by ``world.progression.services.xp_ledger``
    on every award and purchase, and hand-editing them would silently resize the
    death-kudos cap (ADR-0131) that reads ``total_spent``.
    """

    autocomplete_fields = ["character"]

    list_display = ["character", "transferable", "total_earned", "total_spent"]
    list_filter = ["transferable", "updated_date"]
    search_fields = ["character__character__db_key"]
    readonly_fields = ["total_earned", "total_spent", "created_date", "updated_date"]


@admin.register(CharacterXPTransaction)
class CharacterXPTransactionAdmin(admin.ModelAdmin):
    """Immutable per-character XP audit trail; add/change disabled like other receipts."""

    autocomplete_fields = ["character"]

    list_display = ["character", "amount", "reason", "description", "transaction_date"]
    list_filter = ["reason", "transferable", "transaction_date"]
    search_fields = ["character__character__db_key", "description"]
    readonly_fields = ["character", "amount", "reason", "description", "transferable"]

    def has_add_permission(self, request, obj=None):  # noqa: ARG002
        return False

    def has_change_permission(self, request, obj=None):  # noqa: ARG002
        return False
