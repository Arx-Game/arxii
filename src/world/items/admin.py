"""Django admin configuration for items."""

from django.contrib import admin

from world.items.models import InteractionType, QualityTier


@admin.register(QualityTier)
class QualityTierAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "color_hex",
        "numeric_min",
        "numeric_max",
        "stat_multiplier",
        "sort_order",
    ]
    ordering = ["sort_order"]


@admin.register(InteractionType)
class InteractionTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "label", "description"]
    search_fields = ["name", "label"]
