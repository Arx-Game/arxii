"""Django admin configuration for items."""

from django.contrib import admin

from world.contributors.admin import CREDIT_FIELDSET
from world.items.crafting.models import (
    AccentArchetypeAllowance,
    AccentExclusion,
    CraftingMaterialRequirement,
    CraftingRecipe,
    CraftingRecipeConsequence,
    CraftingRecipeModifier,
    CraftingSkillCap,
    ItemAccent,
)
from world.items.models import (
    AccentLevel,
    Adornment,
    AudacityTuning,
    DisguiseKitEffect,
    EquippedItem,
    FashionStyle,
    FashionStyleBonus,
    GarmentMitigation,
    GemDetails,
    GemGrade,
    GemInstanceDetails,
    InteractionType,
    ItemCheckModifier,
    ItemInstance,
    ItemStyle,
    ItemTemplate,
    ItemTemplateAppearanceEffect,
    ItemTemplateProperty,
    Mantle,
    MantleLevelDefinition,
    MaterialBucket,
    MaterialCategory,
    OrgMaterialLedgerEntry,
    OrgMaterialStock,
    OwnershipEvent,
    PendingRareFind,
    QualityTier,
    RecycleRequest,
    Silhouette,
    StreamMaterialPool,
    Style,
    TemplateInteraction,
    TemplateSlot,
    WeaponClass,
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


@admin.register(MaterialBucket)
class MaterialBucketAdmin(admin.ModelAdmin):
    list_display = ["character_sheet", "material_category", "value"]
    list_filter = ["material_category"]
    raw_id_fields = ["character_sheet"]  # large CharacterSheet table


@admin.register(StreamMaterialPool)
class StreamMaterialPoolAdmin(admin.ModelAdmin):
    list_display = ["income_stream", "material_category", "uncollected_value"]
    list_filter = ["material_category"]
    raw_id_fields = ["income_stream"]  # large OrgIncomeStream table


@admin.register(PendingRareFind)
class PendingRareFindAdmin(admin.ModelAdmin):
    list_display = ["gem_instance", "income_stream", "accrued_at"]
    raw_id_fields = ["income_stream", "gem_instance"]  # large tables


@admin.register(OrgMaterialStock)
class OrgMaterialStockAdmin(admin.ModelAdmin):
    list_display = ["organization", "material_category", "value", "asking_price_pct"]
    list_filter = ["material_category"]
    raw_id_fields = ["organization"]  # large Organization table


@admin.register(OrgMaterialLedgerEntry)
class OrgMaterialLedgerEntryAdmin(admin.ModelAdmin):
    list_display = [
        "organization",
        "material_category",
        "kind",
        "value",
        "counterparty_sheet",
        "created_at",
    ]
    list_filter = ["kind", "material_category"]
    raw_id_fields = ["organization", "counterparty_sheet"]  # large tables


@admin.register(AccentLevel)
class AccentLevelAdmin(admin.ModelAdmin):
    list_display = ["level", "name"]
    ordering = ["level"]


@admin.register(ItemAccent)
class ItemAccentAdmin(admin.ModelAdmin):
    list_display = ["item_instance", "target", "level"]
    list_filter = ["target", "level"]
    raw_id_fields = ["item_instance"]  # large ItemInstance table


@admin.register(AccentExclusion)
class AccentExclusionAdmin(admin.ModelAdmin):
    list_display = ["target_a", "target_b"]


@admin.register(AccentArchetypeAllowance)
class AccentArchetypeAllowanceAdmin(admin.ModelAdmin):
    list_display = ["target", "gear_archetype"]
    list_filter = ["target"]


@admin.register(RecycleRequest)
class RecycleRequestAdmin(admin.ModelAdmin):
    """GM sign-off surface for story-protected recycling (#2886) — approve or
    deny by editing status + resolved_by until a GM panel lands."""

    list_display = ["item_instance", "requested_by", "status", "created_at", "resolved_by"]
    list_filter = ["status"]
    raw_id_fields = ["item_instance", "requested_by"]  # large tables


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


@admin.register(WeaponClass)
class WeaponClassAdmin(admin.ModelAdmin):
    list_display = ("name", "strength_tenths", "gear_archetype", "default_damage")
    search_fields = ("name",)


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


class ItemCheckModifierInline(admin.TabularInline):
    model = ItemCheckModifier
    extra = 1
    autocomplete_fields = ["check_type"]
    verbose_name = "Check Modifier"
    verbose_name_plural = "Check Modifiers"


class ItemTemplatePropertyInline(admin.TabularInline):
    model = ItemTemplateProperty
    extra = 1
    autocomplete_fields = ["property"]
    verbose_name = "Default Property"
    verbose_name_plural = "Default Properties"


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
        "weapon_class",
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
                    "weapon_class",
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
            "Mechanics: consumable & on-use",
            {
                "fields": [
                    "is_consumable",
                    "max_charges",
                    "on_use_pool",
                    "on_use_check_type",
                    "on_use_difficulty",
                    "on_use_target_kind",
                    "requires_attunement",
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
        CREDIT_FIELDSET,
    ]
    inlines = [
        TemplateSlotInline,
        TemplateInteractionInline,
        GarmentMitigationInline,
        ItemTemplateAppearanceEffectInline,
        DisguiseKitEffectInline,
        ItemCheckModifierInline,
        ItemTemplatePropertyInline,
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
    list_display = ("name", "origin", "era", "founder", "audacity")
    list_filter = ("era", "audacity")
    search_fields = ["name", "origin"]
    autocomplete_fields = ["founder"]


@admin.register(Silhouette)
class SilhouetteAdmin(admin.ModelAdmin):
    list_display = ("name", "wear_family", "parent", "exposes_beneath", "is_active")
    list_filter = ("wear_family", "exposes_beneath", "is_active")
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


# ---------------------------------------------------------------------------
# #3831
# ---------------------------------------------------------------------------


class CraftingMaterialRequirementInline(admin.TabularInline):
    model = CraftingMaterialRequirement
    extra = 1
    autocomplete_fields = ["item_template", "material_category"]


class CraftingRecipeConsequenceInline(admin.TabularInline):
    model = CraftingRecipeConsequence
    extra = 1
    autocomplete_fields = ["consequence"]


class CraftingRecipeModifierInline(admin.TabularInline):
    model = CraftingRecipeModifier
    extra = 1
    autocomplete_fields = ["target"]


@admin.register(CraftingRecipe)
class CraftingRecipeAdmin(admin.ModelAdmin):
    """#3831 - the top-level authored recipe driving a crafting workflow."""

    list_display = [
        "name",
        "kind",
        "check_type",
        "requires_station",
        "requires_knowledge",
    ]
    list_filter = ["kind", "requires_station", "requires_knowledge", "default_cost_consumption"]
    search_fields = ["name"]
    list_select_related = ["check_type"]
    autocomplete_fields = [
        "check_type",
        "skill_trait",
        "specialization",
        "required_feature_kind",
        "output_item_template",
    ]
    inlines = [
        CraftingMaterialRequirementInline,
        CraftingRecipeConsequenceInline,
        CraftingRecipeModifierInline,
    ]


@admin.register(CraftingMaterialRequirement)
class CraftingMaterialRequirementAdmin(admin.ModelAdmin):
    """#3831 - one ingredient requirement for a crafting recipe."""

    list_display = ["recipe", "item_template", "material_category", "quantity"]
    list_filter = ["material_category"]
    search_fields = ["recipe__name", "item_template__name"]
    autocomplete_fields = ["recipe", "item_template", "material_category"]


@admin.register(CraftingSkillCap)
class CraftingSkillCapAdmin(admin.ModelAdmin):
    """#3831 - the minimum-skill-to-max-quality-tier ladder for a recipe."""

    list_display = ["recipe", "min_skill_value", "max_quality_tier"]
    search_fields = ["recipe__name"]
    autocomplete_fields = ["recipe"]


@admin.register(CraftingRecipeConsequence)
class CraftingRecipeConsequenceAdmin(admin.ModelAdmin):
    """#3831 - a weighted consequence pool entry for a crafting recipe."""

    list_display = ["recipe", "consequence", "weight_override", "cost_consumption"]
    list_filter = ["cost_consumption"]
    search_fields = ["recipe__name", "consequence__label"]
    autocomplete_fields = ["recipe", "consequence"]


@admin.register(CraftingRecipeModifier)
class CraftingRecipeModifierAdmin(admin.ModelAdmin):
    """#3831 - a modifier outcome a crafting recipe grants on the output item."""

    list_display = ["recipe", "target", "base_value", "quality_scale_factor"]
    search_fields = ["recipe__name", "target__name"]
    autocomplete_fields = ["recipe", "target"]


class MantleLevelDefinitionInline(admin.TabularInline):
    model = MantleLevelDefinition
    extra = 1
    autocomplete_fields = ["codex_entry_required"]


@admin.register(Mantle)
class MantleAdmin(admin.ModelAdmin):
    """#3831 - an attunable artifact and its authored attunement levels."""

    list_display = ["name", "item_instance", "is_active", "max_level"]
    list_filter = ["is_active"]
    search_fields = ["name"]
    raw_id_fields = ["item_instance"]
    inlines = [MantleLevelDefinitionInline]


@admin.register(MantleLevelDefinition)
class MantleLevelDefinitionAdmin(admin.ModelAdmin):
    """#3831 - one authored mantle attunement level and its research gate."""

    list_display = ["mantle", "level", "codex_entry_required"]
    search_fields = ["mantle__name"]
    autocomplete_fields = ["mantle", "codex_entry_required"]


# The market submodule keeps its own admin next to its models; Django only
# autoloads <app>/admin.py, so import it here to register those models (#2862).
from world.items.market import admin as _market_admin  # noqa: E402, F401

# Same for the trade submodule (#2990).
from world.items.trade import admin as _trade_admin  # noqa: E402, F401
