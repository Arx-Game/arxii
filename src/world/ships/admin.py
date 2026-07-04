"""Admin registrations for the ships system (#1832 Task 10)."""

from __future__ import annotations

from typing import ClassVar

from django.contrib import admin

from world.ships.models import ShipDeployment, ShipDetails, ShipType


@admin.register(ShipType)
class ShipTypeAdmin(admin.ModelAdmin):
    """The authored ship-type catalog — names and PLACEHOLDER base stats are content."""

    list_display: ClassVar[list[str]] = [
        "name",
        "base_hull",
        "base_handling",
        "base_armament",
        "base_crew_capacity",
        "base_cargo_capacity",
    ]
    search_fields: ClassVar[list[str]] = ["name"]


@admin.register(ShipDetails)
class ShipDetailsAdmin(admin.ModelAdmin):
    """Per-Building ship extension — inspect persistent investment/repair state."""

    list_display: ClassVar[list[str]] = [
        "building",
        "ship_type",
        "handling_level",
        "armament_level",
        "needs_repair",
    ]
    list_filter: ClassVar[list[str]] = ["ship_type", "needs_repair"]


@admin.register(ShipDeployment)
class ShipDeploymentAdmin(admin.ModelAdmin):
    """Links between a persistent ship and its in-battle vehicle."""

    list_display: ClassVar[list[str]] = ["ship", "battle", "vehicle", "created_at"]
    list_filter: ClassVar[list[str]] = ["battle"]
