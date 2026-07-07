"""Django admin configuration for items."""

from django.contrib import admin

from world.items.models import (
    AudacityTuning,
    CurrencyBalance,
    EquippedItem,
    FashionStyle,
    FashionStyleBonus,
    GarmentMitigation,
    InteractionType,
    ItemInstance,
    ItemStyle,
    ItemTemplate,
    OwnershipEvent,
    QualityTier,
    Style,
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


class GarmentMitigationInline(admin.TabularInline):
    model = GarmentMitigation
    extra = 1
    raw_id_fields = ["resonance"]


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
        "gear_archetype",
    ]
    search_fields = ["name"]
    list_select_related = ["minimum_quality_tier", "image"]
    raw_id_fields = ["image", "weapon_damage_type"]
    inlines = [TemplateSlotInline, TemplateInteractionInline, GarmentMitigationInline]


class ItemStyleInline(admin.TabularInline):
    model = ItemStyle
    extra = 1
    autocomplete_fields = ["style"]


@admin.register(ItemInstance)
class ItemInstanceAdmin(admin.ModelAdmin):
    list_display = [
        "display_name",
        "template",
        "quality_tier",
        "quantity",
        "durability",
        "holder_character_sheet",
        "crafter_character_sheet",
    ]
    list_filter = ["quality_tier", "template"]
    readonly_fields = ["is_broken"]
    list_select_related = [
        "template",
        "quality_tier",
        "holder_character_sheet",
        "crafter_character_sheet",
        "crafter_persona_display",
        "image",
    ]
    search_fields = ["custom_name", "template__name"]
    raw_id_fields = [
        "game_object",
        "holder_character_sheet",
        "crafter_character_sheet",
        "crafter_persona_display",
        "image",
    ]
    inlines = [ItemStyleInline]


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
        "from_character_sheet",
        "to_character_sheet",
        "created_at",
    ]
    list_filter = ["event_type"]
    list_select_related = [
        "item_instance",
        "from_character_sheet",
        "to_character_sheet",
        "from_persona_display",
        "to_persona_display",
    ]
    raw_id_fields = [
        "item_instance",
        "from_character_sheet",
        "to_character_sheet",
        "from_persona_display",
        "to_persona_display",
    ]
    readonly_fields = ["created_at"]


@admin.register(CurrencyBalance)
class CurrencyBalanceAdmin(admin.ModelAdmin):
    list_display = ["character", "gold"]
    list_select_related = ["character"]
    raw_id_fields = ["character"]


class FashionStyleBonusInline(admin.TabularInline):
    model = FashionStyleBonus
    extra = 1
    autocomplete_fields = ["target"]


@admin.register(FashionStyle)
class FashionStyleAdmin(admin.ModelAdmin):
    list_display = ["name", "description"]
    search_fields = ["name"]
    filter_horizontal = ["in_vogue_facets"]
    inlines = [FashionStyleBonusInline]


@admin.register(Style)
class StyleAdmin(admin.ModelAdmin):
    list_display = ("name", "audacity")
    list_filter = ("audacity",)
    search_fields = ["name"]


@admin.register(AudacityTuning)
class AudacityTuningAdmin(admin.ModelAdmin):
    """Singleton tuning config for the per-audacity-tier reward multiplier (#2029)."""

    list_display = (
        "pk",
        "understated_mult",
        "expressive_mult",
        "bold_mult",
        "outrageous_mult",
    )

    def has_add_permission(self, request) -> bool:  # noqa: ARG002
        return not AudacityTuning.objects.exists()

    def has_delete_permission(self, request, obj=None) -> bool:  # noqa: ARG002
        return False
