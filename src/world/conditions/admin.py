from django.contrib import admin

from world.conditions.models import (
    CapabilityType,
    CheckType,
    ConditionCapabilityEffect,
    ConditionCategory,
    ConditionCheckModifier,
    ConditionConditionInteraction,
    ConditionDamageInteraction,
    ConditionDamageOverTime,
    ConditionInstance,
    ConditionResistanceModifier,
    ConditionStage,
    ConditionTemplate,
    DamageType,
)

# =============================================================================
# Lookup Table Admins
# =============================================================================


@admin.register(ConditionCategory)
class ConditionCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "is_negative", "display_order"]
    list_editable = ["display_order"]
    search_fields = ["name"]


@admin.register(CapabilityType)
class CapabilityTypeAdmin(admin.ModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]


@admin.register(CheckType)
class CheckTypeAdmin(admin.ModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]


@admin.register(DamageType)
class DamageTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "resonance", "color_hex"]
    list_filter = ["resonance"]
    search_fields = ["name"]


# =============================================================================
# Condition Template Inlines
# =============================================================================


class ConditionStageInline(admin.TabularInline):
    model = ConditionStage
    extra = 0
    ordering = ["stage_order"]


class ConditionCapabilityEffectInline(admin.TabularInline):
    model = ConditionCapabilityEffect
    extra = 0
    autocomplete_fields = ["capability", "stage"]


class ConditionCheckModifierInline(admin.TabularInline):
    model = ConditionCheckModifier
    extra = 0
    autocomplete_fields = ["check_type", "stage"]


class ConditionResistanceModifierInline(admin.TabularInline):
    model = ConditionResistanceModifier
    extra = 0
    autocomplete_fields = ["damage_type", "stage"]


class ConditionDamageOverTimeInline(admin.TabularInline):
    model = ConditionDamageOverTime
    extra = 0
    autocomplete_fields = ["damage_type", "stage"]


class ConditionDamageInteractionInline(admin.TabularInline):
    model = ConditionDamageInteraction
    fk_name = "condition"
    extra = 0
    autocomplete_fields = ["damage_type", "applies_condition"]


class ConditionConditionInteractionInline(admin.TabularInline):
    model = ConditionConditionInteraction
    fk_name = "condition"
    extra = 0
    autocomplete_fields = ["other_condition", "result_condition"]


# =============================================================================
# Condition Template Admin
# =============================================================================


@admin.register(ConditionTemplate)
class ConditionTemplateAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "category",
        "default_duration_type",
        "is_stackable",
        "has_progression",
        "can_be_dispelled",
        "display_priority",
    ]
    list_filter = [
        "category",
        "is_stackable",
        "has_progression",
        "can_be_dispelled",
        "default_duration_type",
        "draws_aggro",
    ]
    search_fields = ["name", "description"]

    fieldsets = [
        (None, {"fields": ["name", "category", "description"]}),
        (
            "Player Descriptions",
            {
                "fields": ["player_description", "observer_description"],
                "classes": ["collapse"],
            },
        ),
        (
            "Duration",
            {
                "fields": ["default_duration_type", "default_duration_value"],
            },
        ),
        (
            "Stacking",
            {
                "fields": ["is_stackable", "max_stacks", "stack_behavior"],
            },
        ),
        (
            "Progression",
            {
                "fields": ["has_progression"],
                "description": "If enabled, add stages using the inline below.",
            },
        ),
        (
            "Removal",
            {
                "fields": ["can_be_dispelled", "cure_check_type", "cure_difficulty"],
            },
        ),
        (
            "Combat",
            {
                "fields": [
                    "affects_turn_order",
                    "turn_order_modifier",
                    "draws_aggro",
                    "aggro_priority",
                ],
                "classes": ["collapse"],
            },
        ),
        (
            "Display",
            {
                "fields": [
                    "icon",
                    "color_hex",
                    "display_priority",
                    "is_visible_to_others",
                ],
            },
        ),
    ]

    inlines = [
        ConditionStageInline,
        ConditionCapabilityEffectInline,
        ConditionCheckModifierInline,
        ConditionResistanceModifierInline,
        ConditionDamageOverTimeInline,
        ConditionDamageInteractionInline,
        ConditionConditionInteractionInline,
    ]


@admin.register(ConditionStage)
class ConditionStageAdmin(admin.ModelAdmin):
    list_display = [
        "condition",
        "stage_order",
        "name",
        "rounds_to_next",
        "severity_multiplier",
    ]
    list_filter = ["condition"]
    search_fields = ["name", "condition__name"]
    autocomplete_fields = ["condition", "resist_check_type"]


# =============================================================================
# Interaction Admins (for standalone management)
# =============================================================================


@admin.register(ConditionDamageInteraction)
class ConditionDamageInteractionAdmin(admin.ModelAdmin):
    list_display = [
        "condition",
        "damage_type",
        "damage_modifier_percent",
        "removes_condition",
        "applies_condition",
    ]
    list_filter = ["removes_condition", "damage_type", "condition__category"]
    search_fields = ["condition__name", "damage_type__name"]
    autocomplete_fields = ["condition", "damage_type", "applies_condition"]


@admin.register(ConditionConditionInteraction)
class ConditionConditionInteractionAdmin(admin.ModelAdmin):
    list_display = [
        "condition",
        "other_condition",
        "trigger",
        "outcome",
        "priority",
    ]
    list_filter = ["trigger", "outcome"]
    search_fields = ["condition__name", "other_condition__name"]
    autocomplete_fields = ["condition", "other_condition", "result_condition"]


# =============================================================================
# Condition Instance Admin (Runtime Debugging)
# =============================================================================


@admin.register(ConditionInstance)
class ConditionInstanceAdmin(admin.ModelAdmin):
    list_display = [
        "target",
        "condition",
        "current_stage",
        "stacks",
        "severity",
        "rounds_remaining",
        "applied_at",
        "is_suppressed",
    ]
    list_filter = [
        "condition__category",
        "condition",
        "is_suppressed",
    ]
    search_fields = [
        "target__db_key",
        "condition__name",
        "source_description",
    ]
    autocomplete_fields = [
        "target",
        "condition",
        "current_stage",
        "source_character",
        "source_power",
    ]
    readonly_fields = ["applied_at"]

    fieldsets = [
        (None, {"fields": ["target", "condition"]}),
        (
            "State",
            {
                "fields": [
                    "current_stage",
                    "stacks",
                    "severity",
                    "is_suppressed",
                    "suppressed_until",
                ],
            },
        ),
        (
            "Timing",
            {
                "fields": [
                    "applied_at",
                    "expires_at",
                    "rounds_remaining",
                    "stage_rounds_remaining",
                ],
            },
        ),
        (
            "Source",
            {
                "fields": [
                    "source_character",
                    "source_power",
                    "source_description",
                ],
            },
        ),
    ]
