from django.contrib import admin

from world.skills.models import (
    CharacterSpecializationValue,
    SkillPointBudget,
    Specialization,
    TrainingAllocation,
)


@admin.register(Specialization)
class SpecializationAdmin(admin.ModelAdmin):
    """Admin for specializations. A skill's own page (its Trait) edits them inline too."""

    list_display = ["name", "parent_skill", "is_active", "display_order"]
    list_filter = ["parent_skill", "is_active"]
    search_fields = ["name", "description", "tooltip", "parent_skill__name"]
    ordering = ["parent_skill__name", "display_order", "name"]


@admin.register(CharacterSpecializationValue)
class CharacterSpecializationValueAdmin(admin.ModelAdmin):
    """Admin for character specialization values."""

    autocomplete_fields = ["character"]

    list_display = [
        "character",
        "specialization",
        "value",
        "display_value",
        "development_points",
    ]
    list_filter = ["specialization__parent_skill"]
    search_fields = ["character__db_key", "specialization__name"]
    ordering = ["character__db_key", "specialization__name"]

    @admin.display(description="Display Value")
    def display_value(self, obj):
        return obj.display_value


@admin.register(SkillPointBudget)
class SkillPointBudgetAdmin(admin.ModelAdmin):
    """Admin for skill point budget configuration."""

    list_display = [
        "path_points",
        "free_points",
        "total_points",
        "points_per_tier",
        "specialization_unlock_threshold",
    ]

    @admin.display(description="Total Points")
    def total_points(self, obj):
        return obj.total_points

    def has_add_permission(self, _request):
        # Only allow one budget row
        return not SkillPointBudget.objects.exists()

    def has_delete_permission(self, _request, _obj=None):
        return False


@admin.register(TrainingAllocation)
class TrainingAllocationAdmin(admin.ModelAdmin):
    """Admin for training allocations."""

    list_display = ["character", "skill", "specialization", "mentor", "ap_amount"]
    list_filter = ["skill", "specialization"]
    raw_id_fields = ["character", "mentor"]
