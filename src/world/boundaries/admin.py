"""Django admin configuration for the boundaries system."""

from django.contrib import admin

from world.boundaries.models import ContentTheme, PlayerBoundary, TreasuredSubject


@admin.register(ContentTheme)
class ContentThemeAdmin(admin.ModelAdmin):
    """Admin interface for ContentTheme."""

    list_display = ["key", "name", "display_order", "is_active"]
    list_editable = ["display_order", "is_active"]
    search_fields = ["key", "name"]
    ordering = ["display_order", "name"]


@admin.register(PlayerBoundary)
class PlayerBoundaryAdmin(admin.ModelAdmin):
    """Admin interface for PlayerBoundary."""

    autocomplete_fields = ["excluded_tenures", "visible_to_tenures"]

    list_display = ["owner", "kind", "theme", "visibility_mode", "created_at"]
    list_filter = ["kind", "visibility_mode", "theme"]
    search_fields = ["owner__account__username"]
    raw_id_fields = ["owner", "theme"]


@admin.register(TreasuredSubject)
class TreasuredSubjectAdmin(admin.ModelAdmin):
    """Admin interface for TreasuredSubject."""

    autocomplete_fields = ["excluded_tenures", "visible_to_tenures"]

    list_display = ["owner", "subject_kind", "subject_label", "created_at"]
    list_filter = ["subject_kind"]
    search_fields = ["subject_label", "owner__roster_entry__character__db_key"]
    raw_id_fields = [
        "owner",
        "subject_sheet",
        "subject_item",
        "subject_society",
        "subject_organization",
    ]
