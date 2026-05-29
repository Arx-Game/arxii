from django.contrib import admin

from world.vitals.models import CharacterVitals


@admin.register(CharacterVitals)
class CharacterVitalsAdmin(admin.ModelAdmin):
    list_display = ["character_sheet", "health", "max_health", "life_state", "died_at"]
    list_filter = ["life_state"]
    search_fields = ["character_sheet__character__db_key"]
