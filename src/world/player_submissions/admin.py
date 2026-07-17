"""Django admin for player submissions."""

from django.contrib import admin

from world.player_submissions.models import (
    BugReport,
    PlayerFeedback,
    PlayerReport,
    SystemErrorReport,
)


@admin.register(SystemErrorReport)
class SystemErrorReportAdmin(admin.ModelAdmin):
    """Auto-captured runtime errors (#1164) — the staff queue's system-error lane."""

    autocomplete_fields = ["actor_persona"]

    list_display = ["exception_type", "label", "occurrence_count", "last_seen", "status"]
    list_filter = ["status", "exception_type", "last_seen"]
    search_fields = ["label", "exception_type", "message", "traceback"]
    readonly_fields = ["signature", "traceback", "first_seen", "last_seen", "occurrence_count"]


@admin.register(PlayerFeedback)
class PlayerFeedbackAdmin(admin.ModelAdmin):
    autocomplete_fields = ["location", "reporter_account", "reporter_persona"]
    list_display = ["id", "reporter_account", "reporter_persona", "status", "created_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["description"]
    readonly_fields = ["created_at"]


@admin.register(BugReport)
class BugReportAdmin(admin.ModelAdmin):
    autocomplete_fields = ["location", "reporter_account", "reporter_persona"]
    list_display = ["id", "reporter_account", "reporter_persona", "status", "created_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["description"]
    readonly_fields = ["created_at"]


@admin.register(PlayerReport)
class PlayerReportAdmin(admin.ModelAdmin):
    autocomplete_fields = [
        "interaction",
        "location",
        "reported_account",
        "reported_persona",
        "reporter_account",
        "reporter_persona",
        "scene",
    ]
    list_display = [
        "id",
        "reporter_account",
        "reporter_persona",
        "reported_account",
        "reported_persona",
        "status",
        "created_at",
    ]
    list_filter = ["status", "created_at"]
    search_fields = ["behavior_description"]
    readonly_fields = ["created_at"]
