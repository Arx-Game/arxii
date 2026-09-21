"""Admin configuration for the relationships app (#3957)."""

from django.contrib import admin
from django.db.models import Count

from world.relationships.models import (
    BondCombatConfig,
    CharacterRelationship,
    GrievanceOption,
    RelationshipAllocation,
    RelationshipCapstone,
    RelationshipCondition,
    RelationshipDepthTransaction,
    RelationshipGrowthConfig,
    RelationshipLabel,
    RelationshipTier,
    RelationshipType,
)

DESCRIPTION_TRUNCATE_LENGTH = 50


@admin.register(GrievanceOption)
class GrievanceOptionAdmin(admin.ModelAdmin):
    list_display = ["label", "conflict_points", "display_order", "is_active"]
    list_editable = ["conflict_points", "display_order", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["label"]


@admin.register(RelationshipCondition)
class RelationshipConditionAdmin(admin.ModelAdmin):
    list_display = ["name", "description_truncated", "display_order", "modifier_count"]
    search_fields = ["name", "description"]
    ordering = ["display_order", "name"]
    list_editable = ["display_order"]
    filter_horizontal = ["gates_modifiers"]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_modifier_count=Count("gates_modifiers"))

    @admin.display(description="Description")
    def description_truncated(self, obj):
        if obj.description and len(obj.description) > DESCRIPTION_TRUNCATE_LENGTH:
            return obj.description[:DESCRIPTION_TRUNCATE_LENGTH] + "..."
        return obj.description or ""

    @admin.display(description="Modifiers")
    def modifier_count(self, obj):
        return obj._modifier_count  # noqa: SLF001


@admin.register(RelationshipType)
class RelationshipTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "family", "valence", "counterpart", "display_order"]
    list_editable = ["display_order"]
    list_filter = ["family", "valence"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ["counterpart"]


@admin.register(RelationshipTier)
class RelationshipTierAdmin(admin.ModelAdmin):
    list_display = ["tier_number", "name", "depth_threshold", "combat_bonus"]
    list_editable = ["name", "depth_threshold", "combat_bonus"]


class RelationshipLabelInline(admin.TabularInline):
    model = RelationshipLabel
    extra = 0
    fields = ["type", "awareness", "since", "ended_at", "replaced", "note"]
    readonly_fields = ["since", "replaced"]
    autocomplete_fields = ["type"]


@admin.register(CharacterRelationship)
class CharacterRelationshipAdmin(admin.ModelAdmin):
    list_display = [
        "source_name",
        "target_name",
        "tier",
        "scene_depth",
        "invested_depth",
        "affection",
        "conflict",
        "is_active",
        "created_at",
    ]
    list_filter = ["is_active", "tier", "is_soul_tether"]
    search_fields = [
        "source__character__db_key",
        "target__character__db_key",
        "target_companion__name",
    ]
    list_select_related = [
        "source",
        "source__character",
        "target",
        "target__character",
        "target_companion",
    ]
    raw_id_fields = ["source", "target", "target_companion"]
    filter_horizontal = ["conditions"]
    readonly_fields = ["created_at", "updated_at"]
    inlines = [RelationshipLabelInline]

    @admin.display(description="Source")
    def source_name(self, obj):
        return obj.source.character.db_key

    @admin.display(description="Target")
    def target_name(self, obj):
        return obj.target_name


@admin.register(RelationshipAllocation)
class RelationshipAllocationAdmin(admin.ModelAdmin):
    list_display = ["relationship", "ap_amount", "game_week", "updated_at"]
    raw_id_fields = ["relationship"]


@admin.register(RelationshipDepthTransaction)
class RelationshipDepthTransactionAdmin(admin.ModelAdmin):
    list_display = ["relationship", "amount", "source", "scene", "game_week", "created_at"]
    list_filter = ["source"]
    raw_id_fields = ["relationship", "scene"]
    readonly_fields = ["created_at"]


@admin.register(RelationshipCapstone)
class RelationshipCapstoneAdmin(admin.ModelAdmin):
    list_display = ["relationship", "tier_claimed", "xp_spent", "is_ritual_capstone", "created_at"]
    list_filter = ["is_ritual_capstone"]
    raw_id_fields = ["relationship", "journal_entry", "ritual"]
    readonly_fields = ["created_at"]


@admin.register(RelationshipGrowthConfig)
class RelationshipGrowthConfigAdmin(admin.ModelAdmin):
    list_display = ["pk", "scene_base_gain", "depth_per_ap", "xp_per_tier", "thread_min_tier"]
    autocomplete_fields = ["updated_by"]


@admin.register(BondCombatConfig)
class BondCombatConfigAdmin(admin.ModelAdmin):
    list_display = ["pk", "min_tier", "soul_tether_multiplier", "updated_at", "updated_by"]
    readonly_fields = ["updated_at"]
    autocomplete_fields = ["updated_by"]
