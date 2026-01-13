"""
Django admin configuration for species app.
"""

from django.contrib import admin

from world.species.models import Language, Species, SpeciesOrigin, SpeciesOriginStatBonus


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


class SpeciesOriginInline(admin.TabularInline):
    """Inline for viewing origins of a species."""

    model = SpeciesOrigin
    extra = 0
    fields = ["name", "description"]
    show_change_link = True


@admin.register(Species)
class SpeciesAdmin(admin.ModelAdmin):
    """Admin for Species model."""

    list_display = ["name", "parent", "sort_order", "origin_count"]
    list_filter = ["parent"]
    search_fields = ["name", "description"]
    ordering = ["sort_order", "name"]
    inlines = [SpeciesChildrenInline, SpeciesOriginInline]

    fieldsets = [
        (None, {"fields": ["name", "parent", "sort_order"]}),
        ("Description", {"fields": ["description"]}),
    ]

    @admin.display(description="Origins")
    def origin_count(self, obj):
        """Show count of origins for this species."""
        return obj.origins.count()


@admin.register(Language)
class LanguageAdmin(admin.ModelAdmin):
    """Admin for Language model."""

    list_display = ["name"]
    search_fields = ["name", "description"]
    ordering = ["name"]


class SpeciesOriginStatBonusInline(admin.TabularInline):
    """Inline for editing stat bonuses on a species origin."""

    model = SpeciesOriginStatBonus
    extra = 1
    fields = ["stat", "value"]


@admin.register(SpeciesOrigin)
class SpeciesOriginAdmin(admin.ModelAdmin):
    """Admin for SpeciesOrigin model."""

    list_display = ["name", "species", "stat_bonus_summary"]
    list_filter = ["species"]
    search_fields = ["name", "description", "species__name"]
    ordering = ["species__name", "name"]
    inlines = [SpeciesOriginStatBonusInline]

    fieldsets = [
        (None, {"fields": ["species", "name"]}),
        ("Description", {"fields": ["description"]}),
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
