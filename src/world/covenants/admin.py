"""Django admin configuration for the covenants system."""

from django.contrib import admin

from world.covenants.models import CovenantRole


@admin.register(CovenantRole)
class CovenantRoleAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "covenant_type", "archetype", "speed_rank"]
    list_filter = ["covenant_type", "archetype"]
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}
