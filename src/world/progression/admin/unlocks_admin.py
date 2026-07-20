"""
Admin interface for progression unlocks models.
"""

from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline

from world.magic.models import ThreadCrossingThreshold
from world.progression.models import (
    AchievementRequirement,
    CharacterUnlock,
    ClassLevelRequirement,
    ClassLevelUnlock,
    ClassXPCost,
    ItemRequirement,
    LevelRequirement,
    MajorGiftTechniqueRequirement,
    MultiClassLevel,
    MultiClassRequirement,
    RelationshipRequirement,
    TierRequirement,
    TraitRatingUnlock,
    TraitRequirement,
    TraitXPCost,
    XPCostChart,
    XPCostEntry,
)

# XP Cost System


class XPCostEntryInline(admin.TabularInline):
    """Inline admin for XP cost entries."""

    model = XPCostEntry
    extra = 1


@admin.register(XPCostChart)
class XPCostChartAdmin(admin.ModelAdmin):
    """Admin interface for XPCostChart."""

    list_display = ["name", "is_active", "cost_entry_count"]
    list_filter = ["is_active"]
    search_fields = ["name", "description"]
    inlines = [XPCostEntryInline]

    def cost_entry_count(self, obj):
        return obj.cost_entries.count()

    cost_entry_count.short_description = "# Entries"


@admin.register(ClassXPCost)
class ClassXPCostAdmin(admin.ModelAdmin):
    """Admin interface for ClassXPCost."""

    list_display = ["character_class", "cost_chart", "cost_modifier_display"]
    list_filter = ["cost_chart", "cost_modifier"]
    search_fields = ["character_class__name", "cost_chart__name"]

    def cost_modifier_display(self, obj):
        return f"{obj.cost_modifier}%"

    cost_modifier_display.short_description = "Cost Modifier"


@admin.register(TraitXPCost)
class TraitXPCostAdmin(admin.ModelAdmin):
    """Admin interface for TraitXPCost."""

    list_display = ["trait", "cost_chart", "cost_modifier_display"]
    list_filter = ["cost_chart", "cost_modifier"]
    search_fields = ["trait__name", "cost_chart__name"]

    def cost_modifier_display(self, obj):
        return f"{obj.cost_modifier}%"

    cost_modifier_display.short_description = "Cost Modifier"


# Unlock Types


@admin.register(ClassLevelUnlock)
class ClassLevelUnlockAdmin(admin.ModelAdmin):
    """Admin interface for ClassLevelUnlock."""

    list_display = ["character_class", "target_level", "get_xp_cost"]
    list_filter = ["character_class", "target_level"]
    search_fields = ["character_class__name"]

    def get_xp_cost(self, obj):
        """Display XP cost if available."""
        try:
            class_cost = ClassXPCost.objects.get(character_class=obj.character_class)
            cost = class_cost.get_cost_for_level(obj.target_level)
            return f"{cost} XP" if cost else "No cost"
        except ClassXPCost.DoesNotExist:
            return "No cost defined"

    get_xp_cost.short_description = "XP Cost"


@admin.register(TraitRatingUnlock)
class TraitRatingUnlockAdmin(admin.ModelAdmin):
    """Admin interface for TraitRatingUnlock."""

    list_display = ["trait", "target_rating_display", "get_xp_cost"]
    list_filter = ["trait__trait_type", "target_rating"]
    search_fields = ["trait__name"]

    def target_rating_display(self, obj):
        return f"{obj.target_rating / 10:.1f}"

    target_rating_display.short_description = "Target Rating"

    def get_xp_cost(self, obj):
        """Display XP cost if available."""
        try:
            trait_cost = TraitXPCost.objects.get(trait=obj.trait)
            cost = trait_cost.get_cost_for_rating(obj.target_rating)
            return f"{cost} XP" if cost else "No cost"
        except TraitXPCost.DoesNotExist:
            return "No cost defined"

    get_xp_cost.short_description = "XP Cost"


# Requirement Models


class RequirementInline(GenericTabularInline):
    """Generic inline for requirements."""

    extra = 0
    readonly_fields = ["content_object"]


@admin.register(TraitRequirement)
class TraitRequirementAdmin(admin.ModelAdmin):
    """Admin interface for TraitRequirement."""

    list_display = [
        "trait",
        "minimum_value_display",
        "class_level_unlock",
        "thread_crossing_threshold",
        "path",
        "is_active",
    ]
    list_filter = [
        "trait__trait_type",
        "is_active",
        "class_level_unlock__character_class",
        "path",
    ]
    search_fields = [
        "trait__name",
        "description",
        "class_level_unlock__character_class__name",
        "path__name",
    ]

    def minimum_value_display(self, obj):
        return f"{obj.minimum_value / 10:.1f}"

    minimum_value_display.short_description = "Min Value"


@admin.register(LevelRequirement)
class LevelRequirementAdmin(admin.ModelAdmin):
    """Admin interface for LevelRequirement."""

    list_display = ["minimum_level", "class_level_unlock", "is_active"]
    list_filter = ["minimum_level", "is_active", "class_level_unlock__character_class"]
    search_fields = ["description", "class_level_unlock__character_class__name"]


@admin.register(ClassLevelRequirement)
class ClassLevelRequirementAdmin(admin.ModelAdmin):
    """Admin interface for ClassLevelRequirement."""

    list_display = [
        "character_class",
        "minimum_level",
        "class_level_unlock",
        "is_active",
    ]
    list_filter = [
        "character_class",
        "minimum_level",
        "is_active",
        "class_level_unlock__character_class",
    ]
    search_fields = [
        "character_class__name",
        "description",
        "class_level_unlock__character_class__name",
    ]


class MultiClassLevelInline(admin.TabularInline):
    """Inline admin for MultiClassLevel."""

    model = MultiClassLevel
    extra = 1


@admin.register(MultiClassRequirement)
class MultiClassRequirementAdmin(admin.ModelAdmin):
    """Admin interface for MultiClassRequirement."""

    list_display = ["__str__", "class_level_unlock", "is_active"]
    list_filter = ["is_active", "class_level_unlock__character_class"]
    search_fields = [
        "description",
        "description_override",
        "class_level_unlock__character_class__name",
    ]
    inlines = [MultiClassLevelInline]


@admin.register(AchievementRequirement)
class AchievementRequirementAdmin(admin.ModelAdmin):
    """Admin interface for AchievementRequirement."""

    list_display = ["achievement", "class_level_unlock", "is_active"]
    list_filter = ["is_active", "class_level_unlock__character_class"]
    search_fields = [
        "achievement__name",
        "description",
        "class_level_unlock__character_class__name",
    ]
    raw_id_fields = ["achievement"]


@admin.register(RelationshipRequirement)
class RelationshipRequirementAdmin(admin.ModelAdmin):
    """Admin interface for RelationshipRequirement."""

    list_display = [
        "required_track_kind",
        "minimum_tier",
        "minimum_count",
        "class_level_unlock",
        "is_active",
    ]
    list_filter = [
        "required_track_kind",
        "minimum_tier",
        "is_active",
        "class_level_unlock__character_class",
    ]
    search_fields = [
        "required_track_kind__name",
        "description",
        "class_level_unlock__character_class__name",
    ]


@admin.register(TierRequirement)
class TierRequirementAdmin(admin.ModelAdmin):
    """Admin interface for TierRequirement."""

    list_display = ["minimum_tier", "class_level_unlock", "is_active"]
    list_filter = ["minimum_tier", "is_active", "class_level_unlock__character_class"]
    search_fields = ["description", "class_level_unlock__character_class__name"]


@admin.register(MajorGiftTechniqueRequirement)
class MajorGiftTechniqueRequirementAdmin(admin.ModelAdmin):
    """Admin interface for MajorGiftTechniqueRequirement (#2440)."""

    list_display = ["minimum_techniques", "class_level_unlock", "is_active"]
    list_filter = ["is_active", "class_level_unlock__character_class"]
    search_fields = ["description", "class_level_unlock__character_class__name"]


# Character Unlocks


@admin.register(CharacterUnlock)
class CharacterUnlockAdmin(admin.ModelAdmin):
    """Admin interface for CharacterUnlock."""

    autocomplete_fields = ["character"]

    list_display = [
        "character",
        "character_class",
        "target_level",
        "xp_spent",
        "unlocked_date",
    ]
    list_filter = ["unlocked_date", "character_class"]
    search_fields = ["character__db_key", "character_class__name"]
    readonly_fields = ["unlocked_date"]


# Thread Crossing Thresholds (#1885)


class TraitRequirementInline(admin.TabularInline):
    """Inline for TraitRequirements attached to a crossing threshold."""

    model = TraitRequirement
    extra = 0
    fields = ["trait", "minimum_value", "is_active", "description"]


class ItemRequirementInline(admin.TabularInline):
    """Inline for ItemRequirements attached to a crossing threshold."""

    model = ItemRequirement
    extra = 0
    fields = ["item_template", "min_touchstone_tier", "quantity", "is_active"]


@admin.register(ThreadCrossingThreshold)
class ThreadCrossingThresholdAdmin(admin.ModelAdmin):
    """Admin interface for ThreadCrossingThreshold.

    Authored catalog of crossing-level requirement gates, keyed on
    ``(target_kind, level)``. Requirements attach via the polymorphic
    ``thread_crossing_threshold`` FK on ``AbstractUnlockRequirement``.
    """

    list_display = ["target_kind", "level", "stage"]
    list_filter = ["target_kind", "stage"]
    search_fields = ["target_kind", "level"]
    inlines = [TraitRequirementInline, ItemRequirementInline]
