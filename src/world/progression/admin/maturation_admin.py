"""Admin for Maturation Point (#2756) and Level Stat Point (#3001) models."""

from django.contrib import admin

from world.progression.models import LevelStatPointSpend, MaturationSpend, MaturationStatCap


@admin.register(MaturationStatCap)
class MaturationStatCapAdmin(admin.ModelAdmin):
    list_display = ["path_stage", "stat_cap"]
    ordering = ["path_stage"]


@admin.register(MaturationSpend)
class MaturationSpendAdmin(admin.ModelAdmin):
    list_display = ["character_sheet", "milestone_year", "trait", "is_active", "created_at"]
    list_filter = ["is_active"]
    raw_id_fields = ["character_sheet", "trait"]
    search_fields = ["character_sheet__character__db_key"]


@admin.register(LevelStatPointSpend)
class LevelStatPointSpendAdmin(admin.ModelAdmin):
    list_display = ["character_sheet", "level_granted", "trait", "is_active", "created_at"]
    list_filter = ["is_active"]
    raw_id_fields = ["character_sheet", "trait"]
    search_fields = ["character_sheet__character__db_key"]
