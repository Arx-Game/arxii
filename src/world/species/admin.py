"""
Django admin configuration for species app.

Note: SpeciesArea and SpeciesAreaStatBonus admin is in character_creation app.
"""

from django.contrib import admin

from world.species.models import Language, Species


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
