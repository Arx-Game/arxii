from django.contrib import admin

from world.events.models import (
    Event,
    EventCatering,
    EventGrandeurContribution,
    EventHost,
    EventInvitation,
    EventModification,
)


class EventHostInline(admin.TabularInline):
    model = EventHost
    extra = 1
    raw_id_fields = ["persona"]


class EventInvitationInline(admin.TabularInline):
    model = EventInvitation
    extra = 0
    raw_id_fields = ["target_persona", "target_organization", "target_society", "invited_by"]


class EventCateringInline(admin.TabularInline):
    model = EventCatering
    extra = 0
    raw_id_fields = ["item_instance", "contributed_by"]


class EventModificationInline(admin.StackedInline):
    model = EventModification
    extra = 0


class EventGrandeurContributionInline(admin.TabularInline):
    model = EventGrandeurContribution
    extra = 0
    raw_id_fields = ["contributed_by", "transfer"]


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ["name", "status", "is_public", "scheduled_real_time", "location"]
    list_filter = ["status", "is_public", "time_phase"]
    search_fields = ["name", "description"]
    raw_id_fields = ["location"]
    inlines = [
        EventHostInline,
        EventInvitationInline,
        EventCateringInline,
        EventGrandeurContributionInline,
        EventModificationInline,
    ]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(EventCatering)
class EventCateringAdmin(admin.ModelAdmin):
    """The catering tags — which vessels and dishes served at which events (#2869)."""

    list_display = ["item_instance", "event", "role", "contributed_by", "created_at"]
    list_filter = ["role"]
    search_fields = ["event__name"]
    raw_id_fields = ["event", "item_instance", "contributed_by"]
    readonly_fields = ["created_at"]


@admin.register(EventGrandeurContribution)
class EventGrandeurContributionAdmin(admin.ModelAdmin):
    """Grandeur spend tags — who paid for what slice of a once-in-a-lifetime event (#2357)."""

    list_display = ["event", "category", "contributed_by", "amount_spent", "created_at"]
    list_filter = ["category"]
    search_fields = ["event__name"]
    raw_id_fields = ["event", "contributed_by", "transfer"]
    readonly_fields = ["created_at"]
