"""Admin registration for proclamations (#2842)."""

from django.contrib import admin

from world.proclamations.models import (
    DomainEdict,
    EdictKind,
    Proclamation,
    StanceArchetype,
)


@admin.register(StanceArchetype)
class StanceArchetypeAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "mercy_delta",
        "method_delta",
        "status_delta",
        "change_delta",
        "allegiance_delta",
        "power_delta",
    )
    search_fields = ("name",)


@admin.register(Proclamation)
class ProclamationAdmin(admin.ModelAdmin):
    list_display = ("issuer", "stance", "org", "check_outcome", "issued_at")
    list_filter = ("check_outcome", "issued_at")
    search_fields = ("prose", "issuer__name")
    raw_id_fields = ("issuer", "org", "stance")


@admin.register(EdictKind)
class EdictKindAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "stance",
        "income_gross_pct",
        "weekly_unrest_delta",
        "weekly_upkeep_coppers",
    )
    search_fields = ("name",)
    raw_id_fields = ("stance",)


@admin.register(DomainEdict)
class DomainEdictAdmin(admin.ModelAdmin):
    list_display = ("domain", "kind", "is_active", "enacted_at", "revoked_at")
    list_filter = ("kind",)
    raw_id_fields = ("domain", "kind", "proclamation")
