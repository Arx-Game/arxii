from django.contrib import admin

from world.narrative.models import Gemit, NarrativeMessage, NarrativeMessageDelivery, UserStoryMute


class NarrativeMessageDeliveryInline(admin.TabularInline):
    model = NarrativeMessageDelivery
    extra = 0
    raw_id_fields = ("recipient_character_sheet",)
    readonly_fields = ("delivered_at", "acknowledged_at")


@admin.register(NarrativeMessage)
class NarrativeMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "category", "sender_account", "related_story", "sent_at")
    list_filter = ("category",)
    search_fields = ("body", "ooc_note")
    readonly_fields = ("sent_at",)
    raw_id_fields = (
        "sender_account",
        "related_story",
        "related_beat_completion",
        "related_episode_resolution",
    )
    inlines = [NarrativeMessageDeliveryInline]


@admin.register(NarrativeMessageDelivery)
class NarrativeMessageDeliveryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "message",
        "recipient_character_sheet",
        "delivered_at",
        "acknowledged_at",
    )
    list_filter = ("delivered_at", "acknowledged_at")
    raw_id_fields = ("message", "recipient_character_sheet")
    readonly_fields = ("delivered_at", "acknowledged_at")


@admin.register(Gemit)
class GemitAdmin(admin.ModelAdmin):
    list_display = ("id", "sender_account", "related_era", "related_story", "sent_at")
    search_fields = ("body",)
    readonly_fields = ("sent_at",)
    raw_id_fields = ("sender_account", "related_era", "related_story")


@admin.register(UserStoryMute)
class UserStoryMuteAdmin(admin.ModelAdmin):
    list_display = ("id", "account", "story", "muted_at")
    raw_id_fields = ("account", "story")
    readonly_fields = ("muted_at",)
