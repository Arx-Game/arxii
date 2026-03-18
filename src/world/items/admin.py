"""Django admin configuration for items."""

from django.contrib import admin

from world.items.models import (
    CurrencyBalance,
    EquippedItem,
    InteractionType,
    ItemInstance,
    ItemTemplate,
    OwnershipEvent,
    QualityTier,
    TemplateInteraction,
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


class TemplateInteractionInline(admin.TabularInline):
    model = TemplateInteraction
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
    list_select_related = ["minimum_quality_tier", "image"]
    raw_id_fields = ["image"]
    inlines = [TemplateSlotInline, TemplateInteractionInline]


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
    list_select_related = ["template", "quality_tier", "owner", "crafter", "image"]
    search_fields = ["custom_name", "template__name"]
    raw_id_fields = ["game_object", "owner", "crafter", "image"]


@admin.register(EquippedItem)
class EquippedItemAdmin(admin.ModelAdmin):
    list_display = [
        "character",
        "item_instance",
        "body_region",
        "equipment_layer",
    ]
    list_filter = ["body_region", "equipment_layer"]
    list_select_related = ["character", "item_instance"]
    raw_id_fields = ["character", "item_instance"]


@admin.register(OwnershipEvent)
class OwnershipEventAdmin(admin.ModelAdmin):
    list_display = [
        "item_instance",
        "event_type",
        "from_account",
        "to_account",
        "created_at",
    ]
    list_filter = ["event_type"]
    list_select_related = [
        "item_instance",
        "from_account",
        "to_account",
    ]
    raw_id_fields = ["item_instance", "from_account", "to_account"]
    readonly_fields = ["created_at"]


@admin.register(CurrencyBalance)
class CurrencyBalanceAdmin(admin.ModelAdmin):
    list_display = ["account", "gold"]
    list_select_related = ["account"]
    raw_id_fields = ["account"]
