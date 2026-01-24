"""Django admin configuration for the action points system."""

from django.contrib import admin

from world.action_points.models import ActionPointConfig, ActionPointPool


@admin.register(ActionPointConfig)
class ActionPointConfigAdmin(admin.ModelAdmin):
    """Admin interface for ActionPointConfig."""

    list_display = [
        "name",
        "default_maximum",
        "daily_regen",
        "weekly_regen",
        "is_active",
    ]
    list_filter = ["is_active"]
    search_fields = ["name"]

    fieldsets = (
        (None, {"fields": ("name", "is_active")}),
        (
            "Default Values",
            {
                "fields": ("default_maximum",),
                "description": "Default maximum AP for new characters.",
            },
        ),
        (
            "Regeneration",
            {
                "fields": ("daily_regen", "weekly_regen"),
                "description": "AP regeneration rates via cron.",
            },
        ),
    )


@admin.register(ActionPointPool)
class ActionPointPoolAdmin(admin.ModelAdmin):
    """Admin interface for ActionPointPool."""

    list_display = [
        "character",
        "current",
        "maximum",
        "banked",
        "last_daily_regen",
    ]
    list_filter = ["last_daily_regen"]
    search_fields = ["character__db_key"]
    readonly_fields = ["last_daily_regen"]
    raw_id_fields = ["character"]

    fieldsets = (
        (None, {"fields": ("character",)}),
        (
            "Action Points",
            {
                "fields": ("current", "maximum", "banked"),
                "description": "Current: available to spend. "
                "Banked: committed to offers. "
                "Maximum: cap for current.",
            },
        ),
        (
            "Timestamps",
            {"fields": ("last_daily_regen",), "classes": ["collapse"]},
        ),
    )
