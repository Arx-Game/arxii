from django.contrib import admin

from world.events.models import Event, EventHost, EventInvitation, EventModification


class EventHostInline(admin.TabularInline):
    model = EventHost
    extra = 1
    raw_id_fields = ["persona"]


class EventInvitationInline(admin.TabularInline):
    model = EventInvitation
    extra = 0
    raw_id_fields = ["target_persona", "target_organization", "target_society", "invited_by"]


class EventModificationInline(admin.StackedInline):
    model = EventModification
    extra = 0


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ["name", "status", "is_public", "scheduled_real_time", "location"]
    list_filter = ["status", "is_public", "time_phase"]
    search_fields = ["name", "description"]
    raw_id_fields = ["location"]
    inlines = [EventHostInline, EventInvitationInline, EventModificationInline]
    readonly_fields = ["created_at", "updated_at"]
