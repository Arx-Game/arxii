"""Django admin configuration for the covenants system."""

from django.contrib import admin

from world.covenants.models import Covenant, CovenantLevelThreshold, CovenantRite, CovenantRole


@admin.register(CovenantRole)
class CovenantRoleAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "covenant_type", "archetype", "speed_rank"]
    list_filter = ["covenant_type", "archetype"]
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Covenant)
class CovenantAdmin(admin.ModelAdmin):
    list_display = ("name", "covenant_type", "level", "formed_at", "dissolved_at")
    list_filter = ("covenant_type",)
    search_fields = ("name",)
    readonly_fields = ("formed_at",)


@admin.register(CovenantLevelThreshold)
class CovenantLevelThresholdAdmin(admin.ModelAdmin):
    list_display = ("level", "required_legend")


@admin.register(CovenantRite)
class CovenantRiteAdmin(admin.ModelAdmin):
    list_display = (
        "ritual",
        "covenant_type",
        "min_covenant_level",
        "min_engaged_present",
        "granted_condition",
        "base_severity",
        "severity_per_extra_participant",
        "max_severity",
    )
    list_filter = ("covenant_type",)
    autocomplete_fields = ("ritual", "granted_condition")
