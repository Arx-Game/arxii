"""Admin configuration for relationships models."""

from django.contrib import admin
from django.db.models import Count

from world.relationships.models import (
    CharacterRelationship,
    HybridRelationshipType,
    HybridRequirement,
    RelationshipCapstone,
    RelationshipChange,
    RelationshipCondition,
    RelationshipDevelopment,
    RelationshipTier,
    RelationshipTrack,
    RelationshipTrackProgress,
    RelationshipUpdate,
)

DESCRIPTION_TRUNCATE_LENGTH = 50


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


@admin.register(RelationshipTrack)
class RelationshipTrackAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "sign", "display_order"]
    list_editable = ["display_order"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(RelationshipTier)
class RelationshipTierAdmin(admin.ModelAdmin):
    list_display = ["track", "name", "tier_number", "point_threshold"]
    list_filter = ["track"]
    search_fields = ["name"]
    list_select_related = ["track"]


@admin.register(HybridRelationshipType)
class HybridRelationshipTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "slug"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(HybridRequirement)
class HybridRequirementAdmin(admin.ModelAdmin):
    list_display = ["hybrid_type", "track", "minimum_tier"]
    list_filter = ["hybrid_type", "track"]
    list_select_related = ["hybrid_type", "track"]


@admin.register(CharacterRelationship)
class CharacterRelationshipAdmin(admin.ModelAdmin):
    list_display = [
        "source_name",
        "target_name",
        "is_active",
        "is_pending",
        "is_deceitful",
        "condition_count",
        "created_at",
    ]
    list_filter = ["is_active", "is_pending", "is_deceitful", "conditions"]
    search_fields = ["source__character__db_key", "target__character__db_key"]
    list_select_related = ["source", "source__character", "target", "target__character"]
    raw_id_fields = ["source", "target"]
    filter_horizontal = ["conditions"]
    readonly_fields = ["created_at", "updated_at"]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_condition_count=Count("conditions"))

    @admin.display(description="Source")
    def source_name(self, obj):
        return obj.source.character.db_key

    @admin.display(description="Target")
    def target_name(self, obj):
        return obj.target.character.db_key

    @admin.display(description="Conditions")
    def condition_count(self, obj):
        return obj._condition_count  # noqa: SLF001


@admin.register(RelationshipTrackProgress)
class RelationshipTrackProgressAdmin(admin.ModelAdmin):
    list_display = ["relationship", "track", "capacity", "developed_points"]
    list_filter = ["track"]
    list_select_related = ["relationship", "track"]


@admin.register(RelationshipUpdate)
class RelationshipUpdateAdmin(admin.ModelAdmin):
    list_display = ["title", "relationship", "track", "points_earned", "visibility", "created_at"]
    list_filter = ["visibility", "is_first_impression", "track"]
    search_fields = ["title"]
    list_select_related = ["relationship", "track"]
    readonly_fields = ["created_at"]


@admin.register(RelationshipDevelopment)
class RelationshipDevelopmentAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "relationship",
        "track",
        "points_earned",
        "xp_awarded",
        "visibility",
        "created_at",
    ]
    list_filter = ["visibility", "track"]
    search_fields = ["title"]
    list_select_related = ["relationship", "track"]
    readonly_fields = ["created_at"]


@admin.register(RelationshipCapstone)
class RelationshipCapstoneAdmin(admin.ModelAdmin):
    list_display = ["title", "relationship", "track", "points", "visibility", "created_at"]
    list_filter = ["visibility", "track"]
    search_fields = ["title"]
    list_select_related = ["relationship", "track"]
    readonly_fields = ["created_at"]


@admin.register(RelationshipChange)
class RelationshipChangeAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "relationship",
        "source_track",
        "target_track",
        "points_moved",
        "visibility",
        "created_at",
    ]
    list_filter = ["visibility", "source_track", "target_track"]
    search_fields = ["title"]
    list_select_related = ["relationship", "source_track", "target_track"]
    readonly_fields = ["created_at"]
