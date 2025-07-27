"""
Django admin configuration for evennia_extensions models.
"""

from django.contrib import admin

from evennia_extensions.models import PlayerAllowList, PlayerBlockList, PlayerData


@admin.register(PlayerData)
class PlayerDataAdmin(admin.ModelAdmin):
    list_display = ["account", "display_name", "karma", "created_date"]
    list_filter = ["hide_from_watch", "private_mode", "created_date"]
    search_fields = ["account__username", "display_name"]
    readonly_fields = ["created_date", "updated_date"]

    fieldsets = (
        ("Account Info", {"fields": ("account", "display_name")}),
        ("Preferences", {"fields": ("karma", "hide_from_watch", "private_mode")}),
        ("Session Info", {"fields": ("last_login_ip",)}),
        ("Staff Notes", {"fields": ("gm_notes",), "classes": ("collapse",)}),
        (
            "Timestamps",
            {"fields": ("created_date", "updated_date"), "classes": ("collapse",)},
        ),
    )


@admin.register(PlayerAllowList)
class PlayerAllowListAdmin(admin.ModelAdmin):
    list_display = ["owner", "allowed_player", "added_date", "notes"]
    list_filter = ["added_date"]
    search_fields = ["owner__account__username", "allowed_player__account__username"]
    readonly_fields = ["added_date"]


@admin.register(PlayerBlockList)
class PlayerBlockListAdmin(admin.ModelAdmin):
    list_display = ["owner", "blocked_player", "blocked_date", "reason"]
    list_filter = ["blocked_date"]
    search_fields = ["owner__account__username", "blocked_player__account__username"]
    readonly_fields = ["blocked_date"]
