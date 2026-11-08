"""
Django admin interface for the traits system.

Provides administrative interfaces for managing trait definitions,
character values, and check resolution configuration.
"""

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError

from world.admin_utils import OneRowPerFormSet, describe_reverse_relations
from world.mechanics.services import ensure_skill_target
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


SKILL_WITH_SPECIALIZATIONS_RETYPED_MESSAGE = (
    "This skill has specializations, so it must stay a Skill. Move or delete its "
    "specializations first."
)


class TraitAdminForm(forms.ModelForm):
    """Refuses retyping a skill that still has specializations away from Skill (#5008).

    No ``Meta``: ``TraitAdmin`` builds the form for ``Trait`` with its own fields.
    """

    def clean(self) -> dict:
        cleaned = super().clean()
        if (
            self.initial.get("trait_type") == TraitType.SKILL
            and cleaned.get("trait_type") != TraitType.SKILL
            and self.instance.specializations.exists()
        ):
            raise ValidationError(SKILL_WITH_SPECIALIZATIONS_RETYPED_MESSAGE)
        return cleaned


@admin.register(Trait)
class TraitAdmin(admin.ModelAdmin):
    """Every trait. Skills are authored on the Skill page, a proxy of this (#5008)."""

    form = TraitAdminForm
    list_display = ["name", "trait_type", "category", "is_public"]
    list_filter = ["trait_type", "category", "is_public"]
    search_fields = ["name", "description"]
    ordering = ["trait_type", "category", "name"]
    inlines = [TraitRankDescriptionInline]
    readonly_fields = ["get_connections"]

    def save_model(self, request, obj, form, change):
        """Save; a skill-type trait gets the modifier target its bonuses land on (#4820)."""
        super().save_model(request, obj, form, change)
        if obj.trait_type == TraitType.SKILL:
            ensure_skill_target(obj)

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
