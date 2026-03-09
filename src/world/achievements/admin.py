"""Django admin configuration for achievements system."""

from django.contrib import admin

from world.achievements.models import (
    Achievement,
    AchievementRequirement,
    AchievementReward,
    CharacterAchievement,
    Discovery,
    RewardDefinition,
    StatDefinition,
    StatTracker,
)


class AchievementRequirementInline(admin.TabularInline):
    """Inline admin for achievement requirements."""

    model = AchievementRequirement
    extra = 1
    raw_id_fields = ["stat"]


class AchievementRewardInline(admin.TabularInline):
    """Inline admin for achievement rewards."""

    model = AchievementReward
    extra = 0
    raw_id_fields = ["reward"]


@admin.register(RewardDefinition)
class RewardDefinitionAdmin(admin.ModelAdmin):
    """Admin for RewardDefinition model."""

    list_display = ["key", "name", "reward_type"]
    list_filter = ["reward_type"]
    search_fields = ["key", "name"]


@admin.register(StatDefinition)
class StatDefinitionAdmin(admin.ModelAdmin):
    """Admin for StatDefinition model."""

    list_display = ["key", "name", "description"]
    search_fields = ["key", "name"]


@admin.register(Achievement)
class AchievementAdmin(admin.ModelAdmin):
    """Admin for Achievement model."""

    list_display = ["name", "notification_level", "hidden", "is_active", "prerequisite"]
    list_filter = ["notification_level", "hidden", "is_active"]
    search_fields = ["name", "description"]
    prepopulated_fields = {"slug": ("name",)}
    inlines = [AchievementRequirementInline, AchievementRewardInline]


@admin.register(StatTracker)
class StatTrackerAdmin(admin.ModelAdmin):
    """Admin for StatTracker model."""

    list_display = ["character_sheet", "stat", "value", "updated_at"]
    list_filter = ["stat"]
    search_fields = ["stat__key", "stat__name"]
    raw_id_fields = ["character_sheet"]


@admin.register(CharacterAchievement)
class CharacterAchievementAdmin(admin.ModelAdmin):
    """Admin for CharacterAchievement model."""

    list_display = ["character_sheet", "achievement", "earned_at", "is_discoverer"]
    list_filter = ["achievement"]
    raw_id_fields = ["character_sheet"]

    @admin.display(boolean=True)
    def is_discoverer(self, obj: CharacterAchievement) -> bool:
        """Return True if the character was a discoverer of this achievement."""
        return obj.discovery_id is not None


@admin.register(Discovery)
class DiscoveryAdmin(admin.ModelAdmin):
    """Admin for Discovery model."""

    list_display = ["achievement", "discovered_at", "discoverer_count"]

    def discoverer_count(self, obj: Discovery) -> int:
        """Return the number of discoverers for this achievement."""
        return obj.discoverers.count()
