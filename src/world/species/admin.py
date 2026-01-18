"""
Django admin configuration for species app.
"""

from django.contrib import admin

from world.species.models import (
    Language,
    Species,
    SpeciesStatBonus,
)


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


class SpeciesStatBonusInline(admin.TabularInline):
    """Inline for editing stat bonuses on a species."""

    model = SpeciesStatBonus
    extra = 1
    fields = ["stat", "value"]


@admin.register(Species)
class SpeciesAdmin(admin.ModelAdmin):
    """Admin for Species model."""

    list_display = ["name", "parent", "sort_order", "stat_bonus_summary", "language_count"]
    list_filter = ["parent"]
    search_fields = ["name", "description"]
    ordering = ["sort_order", "name"]
    filter_horizontal = ["starting_languages"]
    inlines = [SpeciesChildrenInline, SpeciesStatBonusInline]

    fieldsets = [
        (None, {"fields": ["name", "parent", "sort_order"]}),
        ("Description", {"fields": ["description"]}),
        ("Languages", {"fields": ["starting_languages"]}),
    ]

    @admin.display(description="Stat Bonuses")
    def stat_bonus_summary(self, obj):
        """Show summary of stat bonuses."""
        bonuses = obj.stat_bonuses.all()
        if not bonuses:
            return "-"
        parts = []
        for bonus in bonuses:
            sign = "+" if bonus.value >= 0 else ""
            parts.append(f"{sign}{bonus.value} {bonus.stat}")
        return ", ".join(parts)

    @admin.display(description="Languages")
    def language_count(self, obj):
        """Show count of starting languages."""
        return obj.starting_languages.count()


@admin.register(Language)
class LanguageAdmin(admin.ModelAdmin):
    """Admin for Language model."""

    list_display = ["name"]
    search_fields = ["name", "description"]
    ordering = ["name"]
