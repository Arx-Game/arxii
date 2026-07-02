"""Django admin configuration for the battles system."""

from django.contrib import admin

from world.battles.models import BattleOutcomeMapping


@admin.register(BattleOutcomeMapping)
class BattleOutcomeMappingAdmin(admin.ModelAdmin):
    list_display = ["outcome", "check_outcome"]
    list_filter = ["outcome"]
