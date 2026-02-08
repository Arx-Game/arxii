"""Check system admin configuration."""

from django.contrib import admin

from world.checks.models import CheckCategory, CheckType, CheckTypeTrait


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


@admin.register(CheckType)
class CheckTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "is_active", "display_order"]
    list_filter = ["category", "is_active"]
    search_fields = ["name", "description"]
    ordering = ["category__display_order", "display_order", "name"]
    list_editable = ["is_active", "display_order"]
    inlines = [CheckTypeTraitInline]
