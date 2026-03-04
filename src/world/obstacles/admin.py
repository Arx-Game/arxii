"""Admin configuration for the obstacles system."""

from django.contrib import admin

from world.obstacles.models import (
    BypassCapabilityRequirement,
    BypassCheckRequirement,
    BypassOption,
    CharacterBypassDiscovery,
    CharacterBypassRecord,
    ObstacleInstance,
    ObstacleProperty,
    ObstacleTemplate,
)


class BypassCapabilityRequirementInline(admin.TabularInline):
    model = BypassCapabilityRequirement
    extra = 1


class BypassCheckRequirementInline(admin.StackedInline):
    model = BypassCheckRequirement
    extra = 0
    max_num = 1


@admin.register(ObstacleProperty)
class ObstaclePropertyAdmin(admin.ModelAdmin):
    list_display = ["name", "description"]
    search_fields = ["name"]


@admin.register(BypassOption)
class BypassOptionAdmin(admin.ModelAdmin):
    list_display = ["name", "obstacle_property", "discovery_type", "resolution_type"]
    list_filter = ["discovery_type", "resolution_type", "obstacle_property"]
    search_fields = ["name"]
    inlines = [BypassCapabilityRequirementInline, BypassCheckRequirementInline]


@admin.register(ObstacleTemplate)
class ObstacleTemplateAdmin(admin.ModelAdmin):
    list_display = ["name", "severity", "blocked_capability"]
    list_filter = ["blocked_capability"]
    search_fields = ["name"]
    filter_horizontal = ["properties"]


@admin.register(ObstacleInstance)
class ObstacleInstanceAdmin(admin.ModelAdmin):
    list_display = ["template", "target", "is_active"]
    list_filter = ["is_active", "template"]
    raw_id_fields = ["target"]


@admin.register(CharacterBypassDiscovery)
class CharacterBypassDiscoveryAdmin(admin.ModelAdmin):
    list_display = ["character", "bypass_option", "discovered_at", "source"]
    raw_id_fields = ["character"]


@admin.register(CharacterBypassRecord)
class CharacterBypassRecordAdmin(admin.ModelAdmin):
    list_display = ["character", "obstacle_instance", "bypass_option", "bypassed_at"]
    raw_id_fields = ["character"]
