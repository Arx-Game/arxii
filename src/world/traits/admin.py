"""
Django admin interface for the traits system.

Provides administrative interfaces for managing trait definitions,
character values, and check resolution configuration.
"""

from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.http import HttpRequest

from world.admin_utils import OneRowPerFormSet, describe_reverse_relations
from world.mechanics.services import ensure_skill_target
from world.skills.models import Specialization
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


SPECIALIZATIONS_ON_NON_SKILL_TRAIT_MESSAGE = (
    "Only a trait of type Skill can have specializations. Set Trait type to Skill, or "
    "clear the Specializations rows."
)


def ensure_skill_target_or_warn(request: HttpRequest, skill: Trait) -> None:
    """Make sure a modifier target points at ``skill``, warning staff if not (#4820).

    A skill rolls a distinction's bonus only through a stat-category ``ModifierTarget``
    whose ``target_trait`` is the skill; without one a pasted ``+10 <skill>`` is refused.
    The Trait page's save calls this for a skill-type trait. An explicit call, not a
    signal (ADR-0009).
    """
    if ensure_skill_target(skill) is None:
        messages.warning(
            request,
            f"No modifier target was made for {skill.name}: another category already "
            "has a target of that name. Retarget that row to this skill on the "
            "Modifier targets admin.",
        )


class SpecializationFormSet(OneRowPerFormSet):
    """Refuses specializations on a trait that is not of type Skill (#5008).

    ``Specialization.parent_skill``'s ``limit_choices_to`` guards its own admin page's
    picker, but an inline sets the parent itself and never runs that check.
    """

    def clean(self) -> None:
        super().clean()
        if self.instance.trait_type == TraitType.SKILL:
            return
        for form in self.forms:
            if form.has_changed() and not self._should_delete_form(form):
                raise ValidationError(SPECIALIZATIONS_ON_NON_SKILL_TRAIT_MESSAGE)


class SpecializationInline(admin.TabularInline):
    """A skill's specializations, authored on its Trait page (#5008)."""

    model = Specialization
    formset = SpecializationFormSet
    extra = 1
    fields = ["name", "tooltip", "display_order", "is_active"]
    ordering = ["display_order", "name"]


@admin.register(Trait)
class TraitAdmin(admin.ModelAdmin):
    """A trait; a skill is a Trait of type Skill, authored here in full (#5008).

    Tooltip, sheet order and the active flag are plain fields, and a skill's
    specializations are an inline.
    """

    list_display = ["name", "trait_type", "category", "is_public", "is_active", "display_order"]
    list_filter = ["trait_type", "category", "is_public", "is_active"]
    search_fields = ["name", "description", "tooltip"]
    ordering = ["trait_type", "category", "name"]
    inlines = [SpecializationInline, TraitRankDescriptionInline]
    readonly_fields = ["get_connections"]

    def get_inline_instances(self, request, obj=None):
        """Hide Specializations on a saved trait that is not a skill and has none.

        The add page always shows it, since the type is chosen in the same form.
        """
        instances = super().get_inline_instances(request, obj)
        if obj is None or obj.trait_type == TraitType.SKILL or obj.specializations.exists():
            return instances
        return [inline for inline in instances if not isinstance(inline, SpecializationInline)]

    def save_model(self, request, obj, form, change):
        """Save the trait; a skill gets the modifier target its bonuses land on (#4820)."""
        super().save_model(request, obj, form, change)
        if obj.trait_type == TraitType.SKILL:
            ensure_skill_target_or_warn(request, obj)

    @admin.display(description="Connections")
    def get_connections(self, obj):
        return describe_reverse_relations(
            obj, exclude=frozenset({"rank_descriptions", "specializations"})
        )


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
