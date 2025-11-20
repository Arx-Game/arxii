"""
Django admin configuration for evennia_extensions models.
"""

from typing import ClassVar

from django.contrib import admin

from evennia_extensions.models import (
    Artist,
    ObjectDisplayData,
    PlayerAllowList,
    PlayerBlockList,
    PlayerData,
    PlayerMedia,
)


@admin.register(PlayerData)
class PlayerDataAdmin(admin.ModelAdmin):
    list_display: ClassVar[list[str]] = [
        "account",
        "display_name",
        "karma",
        "created_date",
        "profile_picture",
    ]
    list_filter: ClassVar[list[str]] = [
        "hide_from_watch",
        "private_mode",
        "created_date",
    ]
    search_fields: ClassVar[list[str]] = ["account__username", "display_name"]
    readonly_fields: ClassVar[list[str]] = ["created_date", "updated_date"]

    fieldsets = (
        ("Account Info", {"fields": ("account", "display_name")}),
        ("Preferences", {"fields": ("karma", "hide_from_watch", "private_mode")}),
        (
            "Media Settings",
            {"fields": ("profile_picture", "max_storage", "max_file_size")},
        ),
        ("Session Info", {"fields": ("last_login_ip",)}),
        ("Staff Notes", {"fields": ("gm_notes",), "classes": ("collapse",)}),
        (
            "Timestamps",
            {"fields": ("created_date", "updated_date"), "classes": ("collapse",)},
        ),
    )


@admin.register(PlayerAllowList)
class PlayerAllowListAdmin(admin.ModelAdmin):
    list_display: ClassVar[list[str]] = [
        "owner",
        "allowed_player",
        "added_date",
        "notes",
    ]
    list_filter: ClassVar[list[str]] = ["added_date"]
    search_fields: ClassVar[list[str]] = [
        "owner__account__username",
        "allowed_player__account__username",
    ]
    readonly_fields: ClassVar[list[str]] = ["added_date"]


@admin.register(PlayerBlockList)
class PlayerBlockListAdmin(admin.ModelAdmin):
    list_display: ClassVar[list[str]] = [
        "owner",
        "blocked_player",
        "blocked_date",
        "reason",
    ]
    list_filter: ClassVar[list[str]] = ["blocked_date"]
    search_fields: ClassVar[list[str]] = [
        "owner__account__username",
        "blocked_player__account__username",
    ]
    readonly_fields: ClassVar[list[str]] = ["blocked_date"]


@admin.register(PlayerMedia)
class PlayerMediaAdmin(admin.ModelAdmin):
    list_display: ClassVar[list[str]] = [
        "player_data",
        "media_type",
        "title",
        "created_by",
        "uploaded_date",
    ]
    list_filter: ClassVar[list[str]] = ["media_type", "uploaded_date"]
    search_fields: ClassVar[list[str]] = ["player_data__account__username", "title"]
    readonly_fields: ClassVar[list[str]] = ["uploaded_date", "updated_date"]


@admin.register(ObjectDisplayData)
class ObjectDisplayDataAdmin(admin.ModelAdmin):
    list_display: ClassVar[list[str]] = [
        "object",
        "longname",
        "colored_name",
        "has_thumbnail",
    ]
    search_fields: ClassVar[list[str]] = ["object__db_key", "longname"]
    readonly_fields: ClassVar[list[str]] = ["created_date", "updated_date"]

    def has_thumbnail(self, obj):
        return bool(obj.thumbnail)

    has_thumbnail.boolean = True
    has_thumbnail.short_description = "Has Thumbnail"


@admin.register(Artist)
class ArtistAdmin(admin.ModelAdmin):
    list_display: ClassVar[list[str]] = ["name", "player_data", "accepting_commissions"]
    list_filter: ClassVar[list[str]] = ["accepting_commissions"]
    search_fields: ClassVar[list[str]] = ["name", "player_data__account__username"]
