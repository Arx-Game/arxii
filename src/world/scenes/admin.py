from django.contrib import admin

from world.scenes.models import (
    Persona,
    Scene,
    SceneMessage,
    SceneMessageSupplementalData,
    SceneParticipation,
)


class SceneMessageInline(admin.TabularInline):
    model = SceneMessage
    extra = 0
    readonly_fields = ["timestamp", "sequence_number"]
    fields = ["persona", "content", "context", "mode", "timestamp", "sequence_number"]


class PersonaInline(admin.TabularInline):
    model = Persona
    extra = 0
    fields = ["name", "description", "character", "thumbnail_url"]


class SceneParticipationInline(admin.TabularInline):
    model = SceneParticipation
    extra = 0
    readonly_fields = ["joined_at", "left_at"]


@admin.register(Scene)
class SceneAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "location",
        "date_started",
        "is_active",
        "is_public",
        "participant_count",
    ]
    list_filter = ["is_active", "is_public", "date_started"]
    search_fields = ["name", "description"]
    readonly_fields = ["date_started"]
    inlines = [SceneParticipationInline, PersonaInline, SceneMessageInline]

    def participant_count(self, obj):
        return obj.participants.count()

    participant_count.short_description = "Participants"


@admin.register(Persona)
class PersonaAdmin(admin.ModelAdmin):
    list_display = ["name", "scene", "account", "character", "created_at"]
    list_filter = ["created_at", "scene__is_active"]
    search_fields = ["name", "scene__name", "account__username"]
    readonly_fields = ["created_at"]


@admin.register(SceneMessage)
class SceneMessageAdmin(admin.ModelAdmin):
    list_display = [
        "persona",
        "scene",
        "context",
        "mode",
        "timestamp",
        "sequence_number",
    ]
    list_filter = ["context", "mode", "timestamp", "scene__is_active"]
    search_fields = ["content", "persona__name", "scene__name"]
    readonly_fields = ["timestamp", "sequence_number"]


@admin.register(SceneMessageSupplementalData)
class SceneMessageSupplementalDataAdmin(admin.ModelAdmin):
    list_display = ["message"]
