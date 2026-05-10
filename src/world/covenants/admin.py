"""Django admin configuration for the covenants system."""

from django.contrib import admin

from world.covenants.models import Covenant, CovenantRole


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
