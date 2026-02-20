from django.contrib import admin

from world.skills.models import (
    CharacterSkillValue,
    CharacterSpecializationValue,
    Skill,
    SkillPointBudget,
    Specialization,
)


class SpecializationInline(admin.TabularInline):
    """Inline admin for specializations under a skill."""

    model = Specialization
    extra = 1
    fields = ["name", "tooltip", "display_order", "is_active"]
    ordering = ["display_order", "name"]


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    """Admin for parent skills."""

    list_display = ["name", "category", "is_active", "display_order"]
    list_filter = ["trait__category", "is_active"]
    search_fields = ["trait__name", "trait__description", "tooltip"]
    ordering = ["display_order", "trait__name"]
    inlines = [SpecializationInline]

    @admin.display(description="Name")
    def name(self, obj):
        return obj.name

    @admin.display(description="Category")
    def category(self, obj):
        return obj.trait.get_category_display()


@admin.register(Specialization)
class SpecializationAdmin(admin.ModelAdmin):
    """Admin for specializations."""

    list_display = ["name", "parent_skill", "is_active", "display_order"]
    list_filter = ["parent_skill", "is_active"]
    search_fields = ["name", "description", "tooltip", "parent_skill__trait__name"]
    ordering = ["parent_skill__trait__name", "display_order", "name"]


@admin.register(CharacterSkillValue)
class CharacterSkillValueAdmin(admin.ModelAdmin):
    """Admin for character skill values."""

    list_display = [
        "character",
        "skill",
        "value",
        "display_value",
        "development_points",
        "rust_points",
    ]
    list_filter = ["skill"]
    search_fields = ["character__db_key", "skill__trait__name"]
    ordering = ["character__db_key", "skill__trait__name"]

    @admin.display(description="Display Value")
    def display_value(self, obj):
        return obj.display_value


@admin.register(CharacterSpecializationValue)
class CharacterSpecializationValueAdmin(admin.ModelAdmin):
    """Admin for character specialization values."""

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
