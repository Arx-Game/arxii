from django.contrib import admin

from world.vitals.models import CharacterVitals


@admin.register(CharacterVitals)
class CharacterVitalsAdmin(admin.ModelAdmin):
    list_display = ["character_sheet", "status", "died_at"]
    list_filter = ["status"]
    search_fields = ["character_sheet__character__db_key"]
