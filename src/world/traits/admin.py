"""
Django admin interface for the traits system.

Provides administrative interfaces for managing trait definitions,
character values, and check resolution configuration.
"""

from django.contrib import admin

from world.admin_utils import OneRowPerFormSet, describe_reverse_relations
from world.skills.admin_inlines import SkillOnTraitInline, ensure_skill_target_or_warn
from world.skills.models import Skill
from world.traits.models import (
    CharacterTraitValue,
    CheckOutcome,
    CheckRank,
    PointConversionRange,
    ResultChart,
    ResultChartOutcome,
    Trait,
    TraitRankDescription,
    TraitType,
)


class TraitRankDescriptionInline(admin.TabularInline):
    model = TraitRankDescription
    formset = OneRowPerFormSet
    extra = 1
    fields = ["value", "display_value", "label", "description"]
    # display_value is a @property, not a DB field — must be declared readonly or
    # the inline's modelform_factory raises FieldError on every Trait change view (#3679).
    readonly_fields = ["display_value"]
    ordering = ["value"]

    @admin.display(description="Display value")
    def display_value(self, obj: TraitRankDescription) -> int | str:
        """The shown value, or blank on the empty add row (#5006).

        The empty row has no value yet, and a stat's display value divides it by ten, so
        reading the model property there raised and every stat trait's page failed.
        """
        if obj.value is None:
            return ""
        return obj.display_value


@admin.register(Trait)
class TraitAdmin(admin.ModelAdmin):
    list_display = ["name", "trait_type", "category", "is_public"]
    list_filter = ["trait_type", "category", "is_public"]
    search_fields = ["name", "description"]
    ordering = ["trait_type", "category", "name"]
    inlines = [SkillOnTraitInline, TraitRankDescriptionInline]
    readonly_fields = ["get_connections"]

    def get_inline_instances(self, request, obj=None):
        """Hide the Skill section on a saved trait that is not a skill and has none (#5006).

        The add page always shows it, since the type is chosen in the same form.
        """
        instances = super().get_inline_instances(request, obj)
        if obj is None or obj.trait_type == TraitType.SKILL or hasattr(obj, "skill"):
            return instances
        return [inline for inline in instances if not isinstance(inline, SkillOnTraitInline)]

    def save_formset(self, request, form, formset, change):
        """Save the inlines; a skill saved here gets its modifier target (#5006, #4820)."""
        if formset.model is not Skill:
            super().save_formset(request, form, formset, change)
            return
        for skill in formset.save():
            ensure_skill_target_or_warn(request, skill)

    @admin.display(description="Connections")
    def get_connections(self, obj):
        return describe_reverse_relations(obj, exclude=frozenset({"rank_descriptions"}))


@admin.register(CharacterTraitValue)
class CharacterTraitValueAdmin(admin.ModelAdmin):
    autocomplete_fields = ["character"]
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
    formset = OneRowPerFormSet
    extra = 1
    ordering = ["min_roll"]


@admin.register(ResultChart)
class ResultChartAdmin(admin.ModelAdmin):
    list_display = ["name", "rank_difference"]
    ordering = ["rank_difference"]
    inlines = [ResultChartOutcomeInline]
