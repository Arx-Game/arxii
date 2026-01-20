from django.contrib import admin

from world.classes.models import Aspect, Path, PathAspect


class PathAspectInline(admin.TabularInline):
    """Inline admin for aspects on a path."""

    model = PathAspect
    extra = 1
    autocomplete_fields = ["aspect"]


@admin.register(Path)
class PathAdmin(admin.ModelAdmin):
    """Admin for character paths."""

    list_display = [
        "name",
        "stage",
        "minimum_level",
        "is_active",
        "parent_count",
        "aspect_summary",
    ]
    list_filter = ["stage", "is_active"]
    search_fields = ["name", "description"]
    filter_horizontal = ["parent_paths"]
    inlines = [PathAspectInline]
    fieldsets = (
        (None, {"fields": ("name", "description", "stage", "minimum_level")}),
        ("Display", {"fields": ("icon_url", "sort_order", "is_active")}),
        ("Evolution", {"fields": ("parent_paths",)}),
    )

    @admin.display(description="Parents")
    def parent_count(self, obj):
        return obj.parent_paths.count()

    @admin.display(description="Aspects")
    def aspect_summary(self, obj):
        return ", ".join(
            f"{pa.aspect.name}({pa.weight})" for pa in obj.path_aspects.select_related("aspect")
        )


@admin.register(Aspect)
class AspectAdmin(admin.ModelAdmin):
    """Admin for aspects."""

    list_display = ["name", "description", "path_count"]
    search_fields = ["name", "description"]

    @admin.display(description="Paths")
    def path_count(self, obj):
        return obj.path_aspects.count()
