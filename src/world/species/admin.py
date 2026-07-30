"""
Django admin configuration for species app.
"""

from django.contrib import admin

from world.species.models import (
    Language,
    Species,
    SpeciesGiftGrant,
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


class SpeciesGiftGrantInline(admin.TabularInline):
    """Inline for editing gift grants (Minor Gift + drawbacks) on a species (#2846)."""

    model = SpeciesGiftGrant
    extra = 0
    fields = [
        "gift",
        "drawback_condition",
        "benefit_condition",
        "drawback_distinction",
        "cg_point_cost",
        "inheritable",
    ]
    autocomplete_fields = ["gift", "drawback_condition", "benefit_condition"]
    raw_id_fields = ["drawback_distinction"]


@admin.register(Species)
class SpeciesAdmin(admin.ModelAdmin):
    """Admin for Species model."""

    list_display = ["name", "parent", "sort_order", "stat_bonus_summary", "language_count"]
    list_filter = ["parent"]
    search_fields = ["name", "description"]
    ordering = ["sort_order", "name"]
    filter_horizontal = ["starting_languages"]
    inlines = [SpeciesChildrenInline, SpeciesStatBonusInline, SpeciesGiftGrantInline]

    fieldsets = [
        (None, {"fields": ["name", "parent", "sort_order"]}),
        ("Description", {"fields": ["description", "codex_entry"]}),
        ("Languages", {"fields": ["starting_languages"]}),
        ("Aging (#2756)", {"fields": ["eternal_youth", "decline_start_age"]}),
    ]
    raw_id_fields = ["codex_entry"]

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


@admin.register(SpeciesGiftGrant)
class SpeciesGiftGrantAdmin(admin.ModelAdmin):
    """Admin for SpeciesGiftGrant (#2846 — previously unregistered)."""

    list_display = [
        "species",
        "gift",
        "drawback_distinction",
        "drawback_condition",
        "cg_point_cost",
        "inheritable",
    ]
    list_filter = ["inheritable", "species"]
    search_fields = ["species__name", "gift__name"]
    autocomplete_fields = ["species", "gift", "drawback_condition", "benefit_condition"]
    raw_id_fields = ["drawback_distinction"]


@admin.register(Language)
class LanguageAdmin(admin.ModelAdmin):
    """Admin for Language model."""

    list_display = ["name"]
    search_fields = ["name", "description"]
    ordering = ["name"]
