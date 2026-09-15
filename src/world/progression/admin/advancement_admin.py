"""
Admin interface for class-level advancement models (#3831).
"""

from django.contrib import admin

from world.progression.models import DuranceTrainingSite


@admin.register(DuranceTrainingSite)
class DuranceTrainingSiteAdmin(admin.ModelAdmin):
    """#3831 - a room registered as a Durance training site, bound to a trainer."""

    list_display = ["room_profile", "officiant", "training_path", "is_active"]
    list_filter = ["is_active", "training_path"]
    search_fields = ["officiant__character__db_key", "training_path__name"]
    raw_id_fields = ["room_profile", "officiant"]
    autocomplete_fields = ["training_path"]
