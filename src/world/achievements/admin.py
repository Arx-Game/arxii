"""Django admin configuration for achievements system."""

from django.contrib import admin

from world.achievements.models import (
    Achievement,
    AchievementRequirement,
    AchievementReward,
    CharacterAchievement,
    Discovery,
    StatTracker,
)


class AchievementRequirementInline(admin.TabularInline):
    """Inline admin for achievement requirements."""

    model = AchievementRequirement
    extra = 1


class AchievementRewardInline(admin.TabularInline):
    """Inline admin for achievement rewards."""

    model = AchievementReward
    extra = 0


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

    list_display = ["character_sheet", "stat_key", "value", "updated_at"]
    list_filter = ["stat_key"]
    search_fields = ["stat_key"]
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
