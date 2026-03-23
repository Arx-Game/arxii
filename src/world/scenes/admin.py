from django.contrib import admin

from world.scenes.models import (
    Interaction,
    InteractionAudience,
    InteractionFavorite,
    Persona,
    PersonaDiscovery,
    Scene,
    SceneMessage,
    SceneMessageReaction,
    SceneMessageSupplementalData,
    SceneParticipation,
    SceneSummaryRevision,
)


class SceneMessageInline(admin.TabularInline):
    model = SceneMessage
    extra = 0
    readonly_fields = ["timestamp", "sequence_number"]
    fields = ["persona", "content", "context", "mode", "timestamp", "sequence_number"]


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
        "privacy_mode",
        "participant_count",
    ]
    list_filter = ["is_active", "privacy_mode", "date_started"]
    search_fields = ["name", "description"]
    readonly_fields = ["date_started"]
    inlines = [SceneParticipationInline, SceneMessageInline]

    def participant_count(self, obj):
        return obj.participants.count()

    participant_count.short_description = "Participants"


@admin.register(Persona)
class PersonaAdmin(admin.ModelAdmin):
    list_display = ["name", "character_identity", "persona_type", "created_at"]
    list_filter = ["persona_type", "created_at"]
    search_fields = ["name", "character__db_key"]
    readonly_fields = ["created_at"]


class SceneMessageSupplementalDataInline(admin.TabularInline):
    model = SceneMessageSupplementalData
    extra = 0


class SceneMessageReactionInline(admin.TabularInline):
    model = SceneMessageReaction
    extra = 0
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
    inlines = [SceneMessageSupplementalDataInline, SceneMessageReactionInline]


class InteractionAudienceInline(admin.TabularInline):
    model = InteractionAudience
    extra = 0


@admin.register(Interaction)
class InteractionAdmin(admin.ModelAdmin):
    list_display = ["persona", "mode", "visibility", "scene", "timestamp"]
    list_filter = ["mode", "visibility"]
    search_fields = ["content"]
    inlines = [InteractionAudienceInline]


@admin.register(InteractionFavorite)
class InteractionFavoriteAdmin(admin.ModelAdmin):
    list_display = ["interaction", "roster_entry", "created_at"]


@admin.register(PersonaDiscovery)
class PersonaDiscoveryAdmin(admin.ModelAdmin):
    list_display = ["persona_a", "persona_b", "discovered_by", "discovered_at"]
    list_filter = ["discovered_at"]


@admin.register(SceneSummaryRevision)
class SceneSummaryRevisionAdmin(admin.ModelAdmin):
    list_display = ["scene", "persona", "action", "timestamp"]
    list_filter = ["action"]
