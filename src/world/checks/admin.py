"""Check system admin configuration."""

from django.contrib import admin

from world.admin_utils import OneRowPerFormSet
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
)
from world.societies.admin_inlines import ConsequenceNamedOrganizationInline


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


class ConsequenceEffectInline(admin.TabularInline):
    model = ConsequenceEffect
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
    autocomplete_fields = ["consequence", "crime_kinds"]
    inlines = [ConsequenceNamedOrganizationInline]

    def get_fieldsets(self, request, obj=None):
        """The effect and its legend award first; every other effect's fields collapsed."""
        named = {*_EFFECT_FIELDS, *_LEGEND_AWARD_FIELDS}
        others = [f for f in self.get_fields(request, obj) if f not in named]
        return (
            (None, {"fields": _EFFECT_FIELDS}),
            ("Legend award", {"fields": _LEGEND_AWARD_FIELDS}),
            ("Other effect fields", {"fields": others, "classes": ["collapse"]}),
        )


@admin.register(Consequence)
class ConsequenceAdmin(admin.ModelAdmin):
    list_display = ["label", "outcome_tier", "weight", "character_loss"]
    list_filter = ["character_loss"]
    search_fields = ["label"]
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
