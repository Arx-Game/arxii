"""Django admin configuration for player channels (#3299)."""

from django.contrib import admin

from world.channels.models import Channel, ChannelBan, ChannelMessage, ChannelSubscription


@admin.register(Channel)
class ChannelAdmin(admin.ModelAdmin):
    list_display = ["name", "kind", "organization", "is_active", "created_at"]
    list_filter = ["kind", "is_active"]
    search_fields = ["name"]
    raw_id_fields = ["organization"]


@admin.register(ChannelMessage)
class ChannelMessageAdmin(admin.ModelAdmin):
    list_display = ["channel", "author_tenure", "created_at"]
    list_filter = ["channel"]
    search_fields = ["body"]
    raw_id_fields = ["channel", "author_tenure"]
    date_hierarchy = "created_at"


@admin.register(ChannelSubscription)
class ChannelSubscriptionAdmin(admin.ModelAdmin):
    list_display = ["channel", "account", "display_tenure", "muted", "notification_level"]
    list_filter = ["muted", "notification_level"]
    raw_id_fields = ["channel", "account", "display_tenure"]


@admin.register(ChannelBan)
class ChannelBanAdmin(admin.ModelAdmin):
    list_display = ["channel", "account", "banned_by", "created_at"]
    raw_id_fields = ["channel", "account", "banned_by"]
