"""Check system admin configuration."""

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet

from world.admin_utils import OneRowPerFormSet
from world.checks.exceptions import ModifierConfigError
from world.checks.models import (
    CheckCall,
    CheckCallTarget,
    CheckCategory,
    CheckType,
    CheckTypeAspect,
    CheckTypeCapabilityModifier,
    CheckTypeSpecialization,
    CheckTypeTrait,
    Consequence,
    ConsequenceEffect,
    ModifierLevelBaseline,
    ModifierSizeFraction,
    ModifierTaper,
    ModifierValue,
)
from world.checks.modifier_values import level_baseline, load_baselines, rank_band_share
from world.checks.types import round_half_up
from world.societies.admin_inlines import ConsequenceNamedOrganizationInline

# Levels the size fraction form shows its derived values at.
_SAMPLE_LEVELS = (1, 6, 11, 16, 21, 26)


class CheckTypeInline(admin.TabularInline):
    model = CheckType
    formset = OneRowPerFormSet
    extra = 0
    fields = ["name", "description", "is_active", "display_order"]


@admin.register(CheckCategory)
class CheckCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "display_order"]
    search_fields = ["name"]
    ordering = ["display_order", "name"]
    list_editable = ["display_order"]
    inlines = [CheckTypeInline]


class CheckTypeTraitInline(admin.TabularInline):
    model = CheckTypeTrait
    formset = OneRowPerFormSet
    extra = 1
    fields = ["trait", "weight"]
    autocomplete_fields = ["trait"]
    ordering = ["-weight", "trait__name"]


class CheckTypeAspectInline(admin.TabularInline):
    model = CheckTypeAspect
    formset = OneRowPerFormSet
    extra = 1
    fields = ["aspect", "weight"]
    autocomplete_fields = ["aspect"]
    ordering = ["-weight"]


class CheckTypeCapabilityModifierInline(admin.TabularInline):
    model = CheckTypeCapabilityModifier
    formset = OneRowPerFormSet
    extra = 1
    fields = ["capability", "weight"]
    autocomplete_fields = ["capability"]
    ordering = ["-weight"]


@admin.register(CheckType)
class CheckTypeAdmin(admin.ModelAdmin):
    autocomplete_fields = ["owner_sheet"]
    list_display = ["name", "category", "is_active", "display_order", "owner_sheet"]
    list_filter = ["category", "is_active"]
    search_fields = ["name", "description"]
    ordering = ["category__display_order", "display_order", "name"]
    list_editable = ["is_active", "display_order"]
    inlines = [CheckTypeTraitInline, CheckTypeAspectInline, CheckTypeCapabilityModifierInline]


# ---------------------------------------------------------------------------
# Consequence system
# ---------------------------------------------------------------------------


class ConsequenceEffectFormSet(BaseInlineFormSet):
    """Runs the trial rules over the whole proposed effect set (#4501).

    The cost rule needs the sibling effects, which an inline form saves after the
    consequence's own ``clean``; the Trial builder runs the same rule over its own set.
    """

    def clean(self) -> None:
        super().clean()
        if any(self.errors):
            return
        proposed = [
            form.instance
            for form in self.forms
            if form.cleaned_data
            and not form.cleaned_data.get("DELETE")
            and form.cleaned_data.get("effect_type")
        ]
        errors = self.instance.trial_rule_errors(proposed)
        if errors:
            raise ValidationError(errors)


class ConsequenceEffectInline(admin.TabularInline):
    model = ConsequenceEffect
    formset = ConsequenceEffectFormSet
    extra = 1
    # #4473: a LEGEND_AWARD effect names organizations on its own page.
    show_change_link = True
    # #2987: crime tags on a LEGEND_AWARD effect are authored here (the content
    # export deliberately drops them: CrimeKind rows are seeder-owned pks).
    autocomplete_fields = ["crime_kinds"]


_EFFECT_FIELDS = ("consequence", "effect_type", "execution_order", "target")
_LEGEND_AWARD_FIELDS = (
    "legend_base_value",
    "legend_source_type",
    "legend_description_template",
    "crime_kinds",
)


_TRIAL_FIELDS = (
    "grants_known",
    "technique",
    "training_points",
    "training_meter_size",
    "grants_technique_outright",
    "scar_is_cosmetic",
)


@admin.register(ConsequenceEffect)
class ConsequenceEffectAdmin(admin.ModelAdmin):
    """One effect of a consequence, on its own page (#4473).

    The Consequence page lists effects inline. A LEGEND_AWARD effect also names the
    organizations the act harmed or helped, which needs a page of its own to hold that inline.
    """

    list_display = ["consequence", "effect_type", "execution_order"]
    list_filter = ["effect_type"]
    search_fields = ["consequence__label"]
    list_select_related = ["consequence"]
    autocomplete_fields = ["consequence", "crime_kinds", "technique"]
    inlines = [ConsequenceNamedOrganizationInline]

    def get_fieldsets(self, request, obj=None):
        """The effect and its legend award first; every other effect's fields collapsed."""
        named = {*_EFFECT_FIELDS, *_LEGEND_AWARD_FIELDS, *_TRIAL_FIELDS}
        others = [f for f in self.get_fields(request, obj) if f not in named]
        return (
            (None, {"fields": _EFFECT_FIELDS}),
            ("Legend award", {"fields": _LEGEND_AWARD_FIELDS}),
            (
                "Trial (#4343)",
                {
                    "fields": _TRIAL_FIELDS,
                    "description": (
                        "grants_known makes a codex entry KNOWN (Success and above). "
                        "Technique training trains or grants a technique; the cosmetic scar "
                        "flag makes a reward scar that is never a cost."
                    ),
                },
            ),
            ("Other effect fields", {"fields": others, "classes": ["collapse"]}),
        )


@admin.register(Consequence)
class ConsequenceAdmin(admin.ModelAdmin):
    list_display = ["label", "outcome_tier", "weight", "character_loss", "deliberately_free"]
    list_filter = ["character_loss", "deliberately_free"]
    search_fields = ["label"]
    # Sorted so the consequence picker on a pool lists labels alphabetically (#4556).
    ordering = ["label"]
    list_select_related = ["outcome_tier"]
    inlines = [ConsequenceEffectInline]


# ---------------------------------------------------------------------------
# Scene check invocation (#3295)
# ---------------------------------------------------------------------------


class CheckCallTargetInline(admin.TabularInline):
    model = CheckCallTarget
    formset = OneRowPerFormSet
    extra = 0
    fields = ["target_sheet", "status", "resolved_at"]
    readonly_fields = ["resolved_at"]
    autocomplete_fields = ["target_sheet"]


@admin.register(CheckCall)
class CheckCallAdmin(admin.ModelAdmin):
    list_display = ["check_type", "band", "scene", "caller_persona", "created_at"]
    list_filter = ["band"]
    list_select_related = ["check_type", "scene", "caller_persona"]
    autocomplete_fields = ["scene", "caller_persona", "check_type"]
    inlines = [CheckCallTargetInline]


@admin.register(CheckTypeSpecialization)
class CheckTypeSpecializationAdmin(admin.ModelAdmin):
    """#3831 - the weighted specialization contribution to a check type (#1688)."""

    list_display = ["check_type", "specialization", "weight"]
    search_fields = ["check_type__name", "specialization__name"]
    list_select_related = ["check_type", "specialization"]
    autocomplete_fields = ["check_type", "specialization"]


@admin.register(ModifierSizeFraction)
class ModifierSizeFractionAdmin(admin.ModelAdmin):
    """How much of one level's width each modifier size is worth in a lane (#5093).

    A modifier's value is its size's fraction times the level width at its level. The
    change form shows what that comes to at a few levels.
    """

    list_display = ["lane", "size", "fraction"]
    list_editable = ["fraction"]
    list_filter = ["lane"]
    ordering = ["lane", "size"]
    readonly_fields = ["derived_values"]

    @admin.display(description="Derived values at levels 1, 6, 11, 16, 21 and 26")
    def derived_values(self, obj: ModifierSizeFraction) -> str:
        if obj.pk is None:
            return "Save the row to see the values it derives."
        baselines = load_baselines(obj.lane)
        shown = []
        for level in _SAMPLE_LEVELS:
            try:
                width = baselines.width(level)
            except ModifierConfigError:
                return f"No {obj.get_lane_display()} level baseline rows cover level {level} yet."
            shown.append(f"level {level}: {max(1, round_half_up(obj.fraction * width))}")
        return "; ".join(shown)


@admin.register(ModifierValue)
class ModifierValueAdmin(admin.ModelAdmin):
    """Overrides of the derived modifier value (#4594, #5093): a row sets what one size
    is worth at one exact level, instead of its fraction times the level width.

    The change form reads the row against the level baseline: its share of that total
    and, on the check lane, the share of a rank band it spans there.
    """

    list_display = ["lane", "size", "level", "value"]
    list_editable = ["value"]
    list_filter = ["lane", "size"]
    ordering = ["lane", "size", "level"]
    readonly_fields = ["read_against_baseline"]

    @admin.display(description="Read against the level baseline")
    def read_against_baseline(self, obj: ModifierValue) -> str:
        if obj.pk is None:
            return "Save the row to read it against the level baseline."
        try:
            baseline = level_baseline(obj.level, obj.lane)
        except ModifierConfigError:
            return f"No level baseline row covers level {obj.level} yet."
        share = rank_band_share(obj.value, baseline)
        band = f"; {share} of a rank band at that total" if share is not None else ""
        return (
            f"A level-{obj.level} character's typical total is {baseline}: this value is "
            f"{obj.value / baseline:.0%} of it{band}."
        )


@admin.register(ModifierLevelBaseline)
class ModifierLevelBaselineAdmin(admin.ModelAdmin):
    """The typical total a character of each level reaches in a lane (#4594)."""

    list_display = ["lane", "level", "baseline"]
    list_editable = ["baseline"]
    list_filter = ["lane"]
    ordering = ["lane", "level"]


@admin.register(ModifierTaper)
class ModifierTaperAdmin(admin.ModelAdmin):
    """Which source kinds taper in a lane, and how lightly (#4594).

    Leave the character's own standing (rollmod, effort, fatigue, strain, soulfray,
    capability) without a row: it never tapers.
    """

    list_display = ["lane", "source_kind", "ratio", "floor"]
    list_editable = ["ratio", "floor"]
    list_filter = ["lane"]
    ordering = ["lane", "source_kind"]
