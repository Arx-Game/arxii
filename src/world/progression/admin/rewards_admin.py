"""
Admin interface for progression rewards models.
"""

from django.contrib import admin

from world.progression.models import (
    DevelopmentPoints,
    DevelopmentTransaction,
    ExperiencePointsData,
    XPTransaction,
)


@admin.register(ExperiencePointsData)
class ExperiencePointsDataAdmin(admin.ModelAdmin):
    """Admin interface for ExperiencePointsData."""

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

    list_display = ["account", "amount", "reason", "description", "transaction_date"]
    list_filter = ["reason", "transaction_date"]
    search_fields = ["account__username", "description"]
    readonly_fields = ["transaction_date"]


@admin.register(DevelopmentPoints)
class DevelopmentPointsAdmin(admin.ModelAdmin):
    """Admin interface for DevelopmentPoints."""

    list_display = ["character", "trait", "total_earned"]
    list_filter = ["trait__trait_type", "updated_date"]
    search_fields = ["character__db_key", "trait__name"]
    readonly_fields = ["created_date", "updated_date"]


@admin.register(DevelopmentTransaction)
class DevelopmentTransactionAdmin(admin.ModelAdmin):
    """Admin interface for DevelopmentTransaction."""

    list_display = [
        "character",
        "trait",
        "source",
        "amount",
        "reason",
        "transaction_date",
    ]
    list_filter = ["source", "reason", "transaction_date"]
    search_fields = ["character__db_key", "trait__name", "description"]
    readonly_fields = ["transaction_date"]
