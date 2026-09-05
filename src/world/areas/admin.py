from django.contrib import admin

from world.areas.models import Area, AreaElevationRequirement


@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    list_display = ["name", "level", "parent", "realm", "grid_x", "grid_y"]
    list_filter = ["level", "realm"]
    search_fields = ["name"]
    autocomplete_fields = ["parent", "realm"]


@admin.register(AreaElevationRequirement)
class AreaElevationRequirementAdmin(admin.ModelAdmin):
    list_display = ["to_level", "min_held_buildings", "min_order_stat", "cost_coppers"]
    list_filter = ["to_level"]
