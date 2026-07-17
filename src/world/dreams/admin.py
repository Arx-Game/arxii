"""Admin for DreamReflection."""

from django.contrib import admin

from world.dreams.models import DreamReflection


@admin.register(DreamReflection)
class DreamReflectionAdmin(admin.ModelAdmin):
    autocomplete_fields = ["descent_target", "dream_room", "waking_room"]
    list_display = ("waking_room", "dream_room", "descent_target", "is_active")
    list_filter = ("is_active",)
    search_fields = ("waking_room__db_key", "dream_room__db_key")
