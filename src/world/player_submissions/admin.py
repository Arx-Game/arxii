"""Django admin for player submissions."""

from django.contrib import admin

from world.player_submissions.models import BugReport, PlayerFeedback, PlayerReport


@admin.register(PlayerFeedback)
class PlayerFeedbackAdmin(admin.ModelAdmin):
    list_display = ["id", "reporter_account", "reporter_persona", "status", "created_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["description"]
    readonly_fields = ["created_at"]


@admin.register(BugReport)
class BugReportAdmin(admin.ModelAdmin):
    list_display = ["id", "reporter_account", "reporter_persona", "status", "created_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["description"]
    readonly_fields = ["created_at"]


@admin.register(PlayerReport)
class PlayerReportAdmin(admin.ModelAdmin):
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
