"""Admin for the military system."""

from __future__ import annotations

from django.contrib import admin

from world.military.models import (
    Army,
    ArmyMembership,
    MilitaryUnit,
    MilitaryUnitCapability,
)


class MilitaryUnitCapabilityInline(admin.TabularInline):
    model = MilitaryUnitCapability
    extra = 0


@admin.register(MilitaryUnit)
class MilitaryUnitAdmin(admin.ModelAdmin):
    list_display = ("name", "owner_org", "commander", "quality", "strength", "morale")
    list_filter = ("quality",)
    search_fields = ("name", "descriptor")
    autocomplete_fields = ("owner_org", "commander", "summoned_by")
    filter_horizontal = ("properties",)
    inlines = [MilitaryUnitCapabilityInline]


class ArmyMembershipInline(admin.TabularInline):
    model = ArmyMembership
    extra = 0
    fk_name = "army"


@admin.register(Army)
class ArmyAdmin(admin.ModelAdmin):
    list_display = ("name", "commander", "covenant", "is_active", "created_at")
    list_filter = ("disbanded_at",)
    search_fields = ("name",)
    autocomplete_fields = ("commander", "covenant", "campaign_story")
    inlines = [ArmyMembershipInline]
