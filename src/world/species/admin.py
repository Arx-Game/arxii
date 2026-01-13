"""
Django admin configuration for species app.
"""

from django.contrib import admin

from world.species.models import Language, Species, SpeciesArea, SpeciesAreaStatBonus


class SpeciesChildrenInline(admin.TabularInline):
    """Inline for viewing subspecies under a parent species."""

    model = Species
    fk_name = "parent"
    extra = 0
    fields = ["name", "sort_order"]
    readonly_fields = ["name"]
    show_change_link = True
    verbose_name = "Subspecies"
    verbose_name_plural = "Subspecies"

    def has_add_permission(self, request, obj=None):  # noqa: ARG002
        return False


@admin.register(Species)
class SpeciesAdmin(admin.ModelAdmin):
    """Admin for Species model."""

    list_display = ["name", "parent", "sort_order", "area_count"]
    list_filter = ["parent"]
    search_fields = ["name", "description"]
    ordering = ["sort_order", "name"]
    inlines = [SpeciesChildrenInline]

    fieldsets = [
        (None, {"fields": ["name", "parent", "sort_order"]}),
        ("Description", {"fields": ["description"]}),
    ]

    @admin.display(description="Areas")
    def area_count(self, obj):
        """Show count of areas this species is available in."""
        return obj.area_options.count()


@admin.register(Language)
class LanguageAdmin(admin.ModelAdmin):
    """Admin for Language model."""

    list_display = ["name"]
    search_fields = ["name", "description"]
    ordering = ["name"]


class SpeciesAreaStatBonusInline(admin.TabularInline):
    """Inline for stat bonuses on SpeciesArea."""

    model = SpeciesAreaStatBonus
    extra = 1
    fields = ["stat", "value"]


@admin.register(SpeciesArea)
class SpeciesAreaAdmin(admin.ModelAdmin):
    """Admin for SpeciesArea through model."""

    list_display = [
        "species",
        "starting_area",
        "trust_required",
        "is_available",
        "cg_point_cost",
        "language_count",
    ]
    list_filter = ["starting_area", "is_available", "trust_required"]
    search_fields = ["species__name", "starting_area__name", "description_override"]
    ordering = ["starting_area__name", "sort_order", "species__name"]
    filter_horizontal = ["starting_languages"]
    inlines = [SpeciesAreaStatBonusInline]

    fieldsets = [
        (None, {"fields": ["species", "starting_area"]}),
        ("Access Control", {"fields": ["trust_required", "is_available"]}),
        ("Costs & Display", {"fields": ["cg_point_cost", "sort_order", "description_override"]}),
        ("Starting Languages", {"fields": ["starting_languages"]}),
    ]

    @admin.display(description="Languages")
    def language_count(self, obj):
        """Show count of starting languages."""
        return obj.starting_languages.count()


@admin.register(SpeciesAreaStatBonus)
class SpeciesAreaStatBonusAdmin(admin.ModelAdmin):
    """Admin for SpeciesAreaStatBonus (mainly for debugging)."""

    list_display = ["species_area", "stat", "value"]
    list_filter = ["stat", "species_area__starting_area"]
    search_fields = ["species_area__species__name"]
