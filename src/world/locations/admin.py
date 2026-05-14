from django.contrib import admin

from world.locations.models import (
    LocationOwnership,
    LocationTenancy,
    LocationValueModifier,
    LocationValueOverride,
)


@admin.register(LocationValueOverride)
class LocationValueOverrideAdmin(admin.ModelAdmin):
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


@admin.register(LocationValueModifier)
class LocationValueModifierAdmin(admin.ModelAdmin):
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


@admin.register(LocationOwnership)
class LocationOwnershipAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "parent_type",
        "holder_type",
        "acquired_at",
        "ended_at",
    )
    list_filter = ("parent_type", "holder_type")
    search_fields = ("notes",)
    autocomplete_fields = (
        "area",
        "room_profile",
        "holder_persona",
        "holder_organization",
    )
    fieldsets = (
        (
            "Where",
            {
                "fields": ("parent_type", "area", "room_profile"),
                "description": (
                    "The location this ownership claim attaches to. "
                    "Cascade resolves at read time — owning an area "
                    "implies owning all rooms within it unless a more-"
                    "specific row overrides."
                ),
            },
        ),
        (
            "Who",
            {
                "fields": ("holder_type", "holder_persona", "holder_organization"),
                "description": (
                    "The owner. Persona for individuals; Organization for "
                    "noble houses, guilds, gangs, businesses, etc."
                ),
            },
        ),
        (
            "Lifecycle",
            {
                "fields": ("acquired_at", "ended_at", "notes"),
                "description": (
                    "Set ended_at to mark the end of this ownership "
                    "(transfer, abandonment, escheat). Historical rows "
                    "form the audit trail."
                ),
            },
        ),
    )


@admin.register(LocationTenancy)
class LocationTenancyAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "parent_type",
        "tenant_type",
        "started_at",
        "ends_at",
    )
    list_filter = ("parent_type", "tenant_type")
    search_fields = ("notes",)
    autocomplete_fields = (
        "area",
        "room_profile",
        "tenant_persona",
        "tenant_organization",
    )
    fieldsets = (
        (
            "Where",
            {
                "fields": ("parent_type", "area", "room_profile"),
                "description": (
                    "The location granted to the tenant. Tenancy on an "
                    "area applies to all rooms within it; tenancy on a "
                    "specific room applies only to that room."
                ),
            },
        ),
        (
            "Who",
            {
                "fields": ("tenant_type", "tenant_persona", "tenant_organization"),
            },
        ),
        (
            "Lifecycle",
            {
                "fields": ("started_at", "ends_at", "notes"),
                "description": (
                    "ends_at NULL = indefinite, revocable. Set to a future "
                    "datetime for a fixed-term lease, or to now() to evict."
                ),
            },
        ),
    )
