"""Check system admin configuration."""

from django.contrib import admin

from world.checks.models import (
    CheckCategory,
    CheckType,
    CheckTypeAspect,
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


@admin.register(CheckType)
class CheckTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "is_active", "display_order"]
    list_filter = ["category", "is_active"]
    search_fields = ["name", "description"]
    ordering = ["category__display_order", "display_order", "name"]
    list_editable = ["is_active", "display_order"]
    inlines = [CheckTypeTraitInline, CheckTypeAspectInline]


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
