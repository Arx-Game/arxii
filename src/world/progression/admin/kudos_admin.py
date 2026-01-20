"""
Admin interface for kudos models.
"""

from django.contrib import admin

from world.progression.models import (
    KudosClaimCategory,
    KudosPointsData,
    KudosSourceCategory,
    KudosTransaction,
)


@admin.register(KudosSourceCategory)
class KudosSourceCategoryAdmin(admin.ModelAdmin):
    """Admin interface for KudosSourceCategory."""

    list_display = ["display_name", "name", "default_amount", "staff_only", "is_active"]
    list_filter = ["is_active", "staff_only"]
    search_fields = ["name", "display_name", "description"]
    ordering = ["display_name"]


@admin.register(KudosClaimCategory)
class KudosClaimCategoryAdmin(admin.ModelAdmin):
    """Admin interface for KudosClaimCategory."""

    list_display = [
        "display_name",
        "name",
        "kudos_cost",
        "reward_amount",
        "is_active",
    ]
    list_filter = ["is_active"]
    search_fields = ["name", "display_name", "description"]
    ordering = ["display_name"]


@admin.register(KudosPointsData)
class KudosPointsDataAdmin(admin.ModelAdmin):
    """Admin interface for KudosPointsData."""

    list_display = ["account", "current_available", "total_earned", "total_claimed"]
    list_filter = ["updated_date"]
    search_fields = ["account__username"]
    readonly_fields = ["created_date", "updated_date", "current_available"]

    def current_available(self, obj):
        return obj.current_available

    current_available.short_description = "Available Kudos"


@admin.register(KudosTransaction)
class KudosTransactionAdmin(admin.ModelAdmin):
    """Admin interface for KudosTransaction."""

    list_display = [
        "account",
        "amount",
        "source_category",
        "claim_category",
        "description",
        "awarded_by",
        "transaction_date",
    ]
    list_filter = ["source_category", "claim_category", "transaction_date"]
    search_fields = ["account__username", "description", "awarded_by__username"]
    readonly_fields = ["transaction_date"]
    raw_id_fields = ["account", "awarded_by", "character"]
