"""Attempt system admin configuration."""

from django.contrib import admin

from world.attempts.models import AttemptCategory, AttemptConsequence, AttemptTemplate


class AttemptTemplateInline(admin.TabularInline):
    model = AttemptTemplate
    extra = 0
    fields = ["name", "check_type", "description", "is_active", "display_order"]
    autocomplete_fields = ["check_type"]


@admin.register(AttemptCategory)
class AttemptCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "display_order"]
    search_fields = ["name"]
    ordering = ["display_order", "name"]
    list_editable = ["display_order"]
    inlines = [AttemptTemplateInline]


class AttemptConsequenceInline(admin.TabularInline):
    model = AttemptConsequence
    extra = 1
    fields = [
        "outcome_tier",
        "label",
        "mechanical_description",
        "weight",
        "character_loss",
        "display_order",
    ]
    ordering = ["outcome_tier__success_level", "display_order"]


@admin.register(AttemptTemplate)
class AttemptTemplateAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "check_type", "is_active", "display_order"]
    list_filter = ["category", "is_active"]
    search_fields = ["name", "description"]
    ordering = ["category__display_order", "display_order", "name"]
    list_editable = ["is_active", "display_order"]
    autocomplete_fields = ["check_type"]
    inlines = [AttemptConsequenceInline]
