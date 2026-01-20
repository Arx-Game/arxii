"""Admin for path-related progression models."""

from django.contrib import admin

from world.progression.models import CharacterPathHistory


@admin.register(CharacterPathHistory)
class CharacterPathHistoryAdmin(admin.ModelAdmin):
    """Admin for character path history."""

    list_display = ["character", "path", "path_stage", "selected_at"]
    list_filter = ["path__stage", "path"]
    search_fields = ["character__db_key", "path__name"]
    ordering = ["character__db_key", "path__stage"]
    raw_id_fields = ["character"]
    autocomplete_fields = ["path"]

    @admin.display(description="Stage")
    def path_stage(self, obj):
        return obj.path.get_stage_display()
