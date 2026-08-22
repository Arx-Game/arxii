"""Django admin configuration for journals."""

from django.contrib import admin

from world.journals.models import JournalBequestGrant, JournalEntry, JournalTag, WeeklyJournalXP


class JournalTagInline(admin.TabularInline):
    model = JournalTag
    extra = 1


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "author",
        "is_public",
        "response_type",
        "posthumous_override",
        "revealed_at",
        "created_at",
    ]
    list_filter = ["is_public", "response_type", "posthumous_override", "created_at"]
    search_fields = ["title", "body", "author__character__db_key"]
    date_hierarchy = "created_at"
    raw_id_fields = ["author", "parent", "revealed_by_settlement"]
    inlines = [JournalTagInline]


@admin.register(JournalBequestGrant)
class JournalBequestGrantAdmin(admin.ModelAdmin):
    list_display = ["recipient_sheet", "deceased_sheet", "created_by_settlement", "created_at"]
    raw_id_fields = ["recipient_sheet", "deceased_sheet", "created_by_settlement"]
    search_fields = [
        "recipient_sheet__character__db_key",
        "deceased_sheet__character__db_key",
    ]


@admin.register(WeeklyJournalXP)
class WeeklyJournalXPAdmin(admin.ModelAdmin):
    autocomplete_fields = ["character_sheet"]
    list_display = [
        "character_sheet",
        "posts_this_week",
        "praised_this_week",
        "retorted_this_week",
        "game_week",
    ]
    search_fields = ["character_sheet__character__db_key"]
