"""Django admin interface for the tarot system."""

from django.contrib import admin

from world.tarot.models import TarotCard


@admin.register(TarotCard)
class TarotCardAdmin(admin.ModelAdmin):
    list_display = ["name", "arcana_type", "suit", "rank", "latin_name"]
    list_filter = ["arcana_type", "suit"]
    search_fields = ["name", "latin_name"]
