from django.contrib import admin, messages
from django.http import HttpRequest

from world.admin_utils import OneRowPerFormSet
from world.mechanics.services import ensure_skill_target
from world.skills.models import (
    CharacterSpecializationValue,
    Skill,
    SkillPointBudget,
    Specialization,
    TrainingAllocation,
)


def ensure_skill_target_or_warn(request: HttpRequest, skill: Skill) -> None:
    """Make sure a modifier target points at ``skill``, warning staff if not (#4820).

    A skill rolls a distinction's bonus only through a stat-category ``ModifierTarget``
    whose ``target_trait`` is the skill; without one a pasted ``+10 <skill>`` is refused.
    An explicit call, not a signal (ADR-0009).
    """
    if ensure_skill_target(skill) is None:
        messages.warning(
            request,
            f"No modifier target was made for {skill.name}: another category already "
            "has a target of that name. Retarget that row to this skill on the "
            "Modifier targets admin.",
        )


class SpecializationInline(admin.TabularInline):
    """Inline admin for specializations under a skill."""

    model = Specialization
    formset = OneRowPerFormSet
    extra = 1
    fields = ["name", "tooltip", "display_order", "is_active"]
    ordering = ["display_order", "name"]


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    """The skill authoring page: a skill is a Trait of type Skill (#5008, #5015)."""

    list_display = ["name", "category", "is_active", "display_order"]
    list_filter = ["category", "is_active"]
    search_fields = ["name", "description", "tooltip"]
    ordering = ["display_order", "name"]
    exclude = ["trait_type"]  # always Skill; Skill.save sets it
    inlines = [SpecializationInline]

    def save_model(self, request, obj, form, change):
        """Save the skill and make sure a modifier target points at its trait (#4820)."""
        super().save_model(request, obj, form, change)
        ensure_skill_target_or_warn(request, obj)


@admin.register(Specialization)
class SpecializationAdmin(admin.ModelAdmin):
    """Admin for specializations."""

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
