"""
Django admin interface for the traits system.

Provides administrative interfaces for managing trait definitions,
character values, and check resolution configuration.
"""

from django.contrib import admin

from world.traits.models import (
    CharacterTraitValue,
    CheckOutcome,
    CheckRank,
    PointConversionRange,
    ResultChart,
    ResultChartOutcome,
    Trait,
    TraitRankDescription,
)


class TraitRankDescriptionInline(admin.TabularInline):
    model = TraitRankDescription
    extra = 1
    fields = ["value", "display_value", "label", "description"]
    ordering = ["value"]


@admin.register(Trait)
class TraitAdmin(admin.ModelAdmin):
    list_display = ["name", "trait_type", "category", "is_public"]
    list_filter = ["trait_type", "category", "is_public"]
    search_fields = ["name", "description"]
    ordering = ["trait_type", "category", "name"]
    inlines = [TraitRankDescriptionInline]


@admin.register(CharacterTraitValue)
class CharacterTraitValueAdmin(admin.ModelAdmin):
    list_display = ["character", "trait", "value", "display_value"]
    list_filter = ["trait__trait_type", "trait__category"]
    search_fields = ["character__db_key", "trait__name"]
    ordering = ["character", "trait"]


@admin.register(PointConversionRange)
class PointConversionRangeAdmin(admin.ModelAdmin):
    list_display = ["trait_type", "min_value", "max_value", "points_per_level"]
    list_filter = ["trait_type"]
    ordering = ["trait_type", "min_value"]


@admin.register(CheckRank)
class CheckRankAdmin(admin.ModelAdmin):
    list_display = ["rank", "name", "min_points"]
    ordering = ["rank"]


@admin.register(CheckOutcome)
class CheckOutcomeAdmin(admin.ModelAdmin):
    list_display = ["name", "success_level", "description"]
    list_filter = ["success_level"]
    search_fields = ["name", "description"]
    ordering = ["success_level", "name"]


class ResultChartOutcomeInline(admin.TabularInline):
    model = ResultChartOutcome
    extra = 1
    ordering = ["min_roll"]


@admin.register(ResultChart)
class ResultChartAdmin(admin.ModelAdmin):
    list_display = ["name", "rank_difference"]
    ordering = ["rank_difference"]
    inlines = [ResultChartOutcomeInline]
