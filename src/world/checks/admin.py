"""Check system admin configuration."""

from django.contrib import admin

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


class CheckTypeInline(admin.TabularInline):
    model = CheckType
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
    extra = 1
    fields = ["trait", "weight"]
    autocomplete_fields = ["trait"]
    ordering = ["-weight", "trait__name"]


class CheckTypeAspectInline(admin.TabularInline):
    model = CheckTypeAspect
    extra = 1
    fields = ["aspect", "weight"]
    autocomplete_fields = ["aspect"]
    ordering = ["-weight"]


class CheckTypeCapabilityModifierInline(admin.TabularInline):
    model = CheckTypeCapabilityModifier
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
