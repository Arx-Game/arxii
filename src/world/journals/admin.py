"""Django admin configuration for journals."""

from django.contrib import admin

from world.journals.models import JournalEntry, JournalTag, WeeklyJournalXP


class JournalTagInline(admin.TabularInline):
    model = JournalTag
    extra = 1


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ["title", "author", "is_public", "response_type", "created_at"]
    list_filter = ["is_public", "response_type", "created_at"]
    search_fields = ["title", "body", "author__character__db_key"]
    date_hierarchy = "created_at"
    raw_id_fields = ["author", "parent"]
    inlines = [JournalTagInline]


@admin.register(WeeklyJournalXP)
class WeeklyJournalXPAdmin(admin.ModelAdmin):
    list_display = [
        "character_sheet",
        "posts_this_week",
        "praised_this_week",
        "retorted_this_week",
        "game_week",
    ]
    search_fields = ["character_sheet__character__db_key"]
