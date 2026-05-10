from django.contrib import admin

from world.locations.models import LocationStatModifier, LocationStatOverride


@admin.register(LocationStatOverride)
class LocationStatOverrideAdmin(admin.ModelAdmin):
    list_display = ("__str__", "parent_type", "stat_key", "value", "last_updated")
    list_filter = ("parent_type", "stat_key")
    search_fields = ("source",)
    autocomplete_fields = ("area", "room_profile")
    readonly_fields = ("last_updated",)
    fieldsets = (
        (
            "What and where",
            {
                "fields": ("parent_type", "area", "room_profile", "stat_key", "value"),
                "description": (
                    "Use Override only for deliberate cascade-cuts (warded "
                    "sanctums, safehouses, magically stabilized chambers). "
                    "For 'this is the normal value at this level' use a "
                    "Modifier with change_per_day=0 instead — overrides "
                    "hide all modifiers in the chain."
                ),
            },
        ),
        ("Audit", {"fields": ("last_updated",)}),
    )


@admin.register(LocationStatModifier)
class LocationStatModifierAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "parent_type",
        "stat_key",
        "value",
        "change_per_day",
        "applied_at",
    )
    list_filter = ("parent_type", "stat_key")
    search_fields = ("source",)
    autocomplete_fields = ("area", "room_profile")
    fieldsets = (
        (
            "What and where",
            {
                "fields": ("parent_type", "area", "room_profile", "stat_key"),
                "description": (
                    "Modifiers stack across the cascade chain. Multiple "
                    "modifiers on the same (parent, stat_key) are allowed "
                    "(rebellion + market-day + noble-house-patrol can all "
                    "stack). parent_type selects which FK is active."
                ),
            },
        ),
        (
            "Magnitude and change",
            {
                "fields": ("value", "change_per_day", "applied_at"),
                "description": (
                    "value is the magnitude at applied_at. change_per_day "
                    "is signed: negative decays toward zero, positive grows "
                    "away from zero, zero is permanent. Read-side computes "
                    "current value lazily."
                ),
            },
        ),
        (
            "Provenance",
            {
                "fields": ("source",),
                "description": (
                    "Free-text label for the originating system. Use to "
                    "bulk-clean by source when a triggering event ends."
                ),
            },
        ),
    )
