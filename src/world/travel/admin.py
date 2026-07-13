"""Admin for the overworld travel system (#1855)."""

from django.contrib import admin

from world.travel.models import (
    TravelHub,
    TravelMethod,
    TravelRoute,
    Voyage,
    VoyageInvite,
    VoyageParticipant,
)


@admin.register(TravelHub)
class TravelHubAdmin(admin.ModelAdmin):
    list_display = ("name", "is_transit_stop", "is_active")
    list_filter = ("is_transit_stop", "is_active")
    search_fields = ("name",)
    raw_id_fields = ("room_profile",)


@admin.register(TravelRoute)
class TravelRouteAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "origin_hub",
        "destination_hub",
        "distance",
        "travel_mode",
        "is_bidirectional",
        "is_active",
    )
    list_filter = ("travel_mode", "is_bidirectional", "is_active")
    search_fields = ("name", "origin_hub__name", "destination_hub__name")
    raw_id_fields = ("origin_hub", "destination_hub")


@admin.register(TravelMethod)
class TravelMethodAdmin(admin.ModelAdmin):
    list_display = ("name", "travel_mode", "base_speed", "is_default")
    list_filter = ("travel_mode", "is_default")
    search_fields = ("name",)
    raw_id_fields = ("ship_type",)


@admin.register(Voyage)
class VoyageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "leader",
        "travel_method",
        "status",
        "current_leg_index",
        "started_at",
    )
    list_filter = ("status",)
    raw_id_fields = (
        "leader",
        "travel_method",
        "origin_hub",
        "destination_hub",
        "ship",
    )


@admin.register(VoyageParticipant)
class VoyageParticipantAdmin(admin.ModelAdmin):
    list_display = ("persona", "voyage", "joined_at", "left_at", "legs_traveled")
    raw_id_fields = ("voyage", "persona")


@admin.register(VoyageInvite)
class VoyageInviteAdmin(admin.ModelAdmin):
    list_display = ("target_persona", "voyage", "response", "invited_at", "responded_at")
    list_filter = ("response",)
    raw_id_fields = ("voyage", "target_persona", "invited_by")
