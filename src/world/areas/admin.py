from django.contrib import admin

from world.areas.models import Area


@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    list_display = ["name", "level", "parent", "realm"]
    list_filter = ["level", "realm"]
    search_fields = ["name"]
    autocomplete_fields = ["parent", "realm"]
    readonly_fields = ["mat_path"]
