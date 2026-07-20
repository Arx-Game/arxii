"""Django admin configuration for the covenants system."""

from django.contrib import admin

from world.covenants.models import (
    Covenant,
    CovenantLevelBonus,
    CovenantLevelThreshold,
    CovenantRite,
    CovenantRole,
    CovenantRoleActionScaling,
    CovenantRoleBonus,
)


@admin.register(CovenantRole)
class CovenantRoleAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "slug",
        "covenant_type",
        "sword_weight",
        "shield_weight",
        "crown_weight",
        "speed_rank",
    ]
    list_filter = ["covenant_type"]
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(CovenantRoleActionScaling)
class CovenantRoleActionScalingAdmin(admin.ModelAdmin):
    list_display = ("action_key", "covenant_role", "thread_level_multiplier")
    list_filter = ("action_key",)
    autocomplete_fields = ("covenant_role",)


@admin.register(Covenant)
class CovenantAdmin(admin.ModelAdmin):
    autocomplete_fields = ["leader"]
    list_display = ("name", "covenant_type", "level", "formed_at", "dissolved_at")
    list_filter = ("covenant_type",)
    search_fields = ("name",)
    readonly_fields = ("formed_at", "provisioning_ratio")


@admin.register(CovenantLevelThreshold)
class CovenantLevelThresholdAdmin(admin.ModelAdmin):
    list_display = ("level", "required_legend")


@admin.register(CovenantRite)
class CovenantRiteAdmin(admin.ModelAdmin):
    list_display = (
        "ritual",
        "covenant_type",
        "min_covenant_level",
        "min_members_present",
        "granted_condition",
        "base_severity",
        "severity_per_extra_participant",
        "max_severity",
    )
    list_filter = ("covenant_type",)
    autocomplete_fields = ("ritual", "granted_condition")


@admin.register(CovenantRoleBonus)
class CovenantRoleBonusAdmin(admin.ModelAdmin):
    list_display = ("covenant_role", "modifier_target", "bonus_per_level")
    list_filter = ("covenant_role__covenant_type",)


@admin.register(CovenantLevelBonus)
class CovenantLevelBonusAdmin(admin.ModelAdmin):
    list_display = ("modifier_target", "bonus_per_level")
