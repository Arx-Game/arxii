"""Django admin configuration for items."""

from django.contrib import admin

from world.items.models import (
    Adornment,
    AudacityTuning,
    CurrencyBalance,
    DisguiseKitEffect,
    EquippedItem,
    FashionStyle,
    FashionStyleBonus,
    GarmentMitigation,
    GemDetails,
    GemGrade,
    GemInstanceDetails,
    InteractionType,
    ItemInstance,
    ItemStyle,
    ItemTemplate,
    ItemTemplateAppearanceEffect,
    MaterialCategory,
    OrgGemStock,
    OwnershipEvent,
    PendingRareFind,
    QualityTier,
    StreamCommonGemPool,
    Style,
    TemplateInteraction,
    TemplateSlot,
)


@admin.register(MaterialCategory)
class MaterialCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "sort_order"]
    search_fields = ["name"]
    ordering = ["sort_order", "name"]


@admin.register(GemGrade)
class GemGradeAdmin(admin.ModelAdmin):
    list_display = ["axis", "sort_order", "label", "multiplier"]
    list_filter = ["axis"]
    ordering = ["axis", "sort_order"]


@admin.register(GemDetails)
class GemDetailsAdmin(admin.ModelAdmin):
    list_display = ["item_template", "quality_level"]
    ordering = ["quality_level"]


@admin.register(GemInstanceDetails)
class GemInstanceDetailsAdmin(admin.ModelAdmin):
    list_display = ["item_instance", "size_grade", "purity_grade", "cut_grade"]
    raw_id_fields = ["item_instance"]


@admin.register(Adornment)
class AdornmentAdmin(admin.ModelAdmin):
    list_display = ["host_instance", "gem_instance", "set_by_account", "set_at"]
    # host_instance / gem_instance → large ItemInstance table; set_by_account → AccountDB.
    raw_id_fields = ["host_instance", "gem_instance", "set_by_account"]


@admin.register(StreamCommonGemPool)
class StreamCommonGemPoolAdmin(admin.ModelAdmin):
    list_display = ["income_stream", "tier", "uncollected_value"]
    list_filter = ["tier"]
    raw_id_fields = ["income_stream"]  # large OrgIncomeStream table


@admin.register(PendingRareFind)
class PendingRareFindAdmin(admin.ModelAdmin):
    list_display = ["gem_instance", "income_stream", "accrued_at"]
    raw_id_fields = ["income_stream", "gem_instance"]  # large tables


@admin.register(OrgGemStock)
class OrgGemStockAdmin(admin.ModelAdmin):
    list_display = ["organization", "tier", "value"]
    list_filter = ["tier"]
    raw_id_fields = ["organization"]  # large Organization table


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


class ItemTemplateAppearanceEffectInline(admin.TabularInline):
    model = ItemTemplateAppearanceEffect
    extra = 1
    autocomplete_fields = ["trait", "target_option"]
    verbose_name = "Appearance Effect"
    verbose_name_plural = "Appearance Effects"


class DisguiseKitEffectInline(admin.TabularInline):
    model = DisguiseKitEffect
    extra = 1
    verbose_name = "Disguise Kit Effect"
    verbose_name_plural = "Disguise Kit Effects"


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
    fieldsets = [
        (None, {"fields": ["name", "description", "is_active"]}),
        (
            "Physical properties",
            {
                "fields": [
                    "weight",
                    "size",
                    "value",
                    "gear_archetype",
                    "base_weapon_damage",
                    "weapon_damage_type",
                    "base_armor_soak",
                    "max_durability",
                    "minimum_quality_tier",
                ]
            },
        ),
        (
            "Container & stack",
            {
                "fields": [
                    "is_container",
                    "container_capacity",
                    "container_max_item_size",
                    "is_stackable",
                    "max_stack_size",
                    "is_wardrobe",
                ],
                "classes": ["collapse"],
            },
        ),
        (
            "Consumable & on-use",
            {
                "fields": [
                    "is_consumable",
                    "max_charges",
                    "on_use_pool",
                    "on_use_check_type",
                    "on_use_difficulty",
                    "on_use_target_kind",
                ],
                "classes": ["collapse"],
            },
        ),
        (
            "Resonance tie",
            {
                "fields": ["tied_resonance", "resonance_tier"],
                "classes": ["collapse"],
            },
        ),
        (
            "Cosmetics",
            {
                "fields": ["supports_open_close", "image"],
                "classes": ["collapse"],
            },
        ),
    ]
    inlines = [
        TemplateSlotInline,
        TemplateInteractionInline,
        GarmentMitigationInline,
        ItemTemplateAppearanceEffectInline,
        DisguiseKitEffectInline,
    ]


class ItemStyleInline(admin.TabularInline):
    model = ItemStyle
    extra = 1
    autocomplete_fields = ["style"]


@admin.register(ItemInstance)
class ItemInstanceAdmin(admin.ModelAdmin):
    autocomplete_fields = [
        "attuned_to_character_sheet",
        "contained_in",
        "designer_character_sheet",
        "designer_persona_display",
    ]
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
    fields = [
        "template",
        "custom_name",
        "custom_description",
        "quality_tier",
        "quantity",
        "charges",
        "durability",
        "is_open",
        "access_policy",
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
