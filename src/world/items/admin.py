"""Django admin configuration for items."""

from django.contrib import admin

from world.items.models import (
    InteractionType,
    ItemInstance,
    ItemTemplate,
    QualityTier,
    TemplateSlot,
)


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


class TemplateSlotInline(admin.TabularInline):
    model = TemplateSlot
    extra = 1


@admin.register(ItemTemplate)
class ItemTemplateAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "weight",
        "size",
        "value",
        "is_active",
        "is_container",
        "is_stackable",
    ]
    list_filter = [
        "is_active",
        "is_container",
        "is_stackable",
        "is_consumable",
        "is_craftable",
    ]
    search_fields = ["name"]
    filter_horizontal = ["interactions", "required_materials"]
    inlines = [TemplateSlotInline]


@admin.register(ItemInstance)
class ItemInstanceAdmin(admin.ModelAdmin):
    list_display = [
        "display_name",
        "template",
        "quality_tier",
        "quantity",
        "owner",
        "crafter",
    ]
    list_filter = ["quality_tier", "template"]
    search_fields = ["custom_name", "template__name"]
    raw_id_fields = ["game_object", "owner", "crafter"]
