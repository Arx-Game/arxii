"""Django admin configuration for boards (#3286)."""

from django.contrib import admin

from world.boards.models import Board, BoardPost


class BoardPostInline(admin.TabularInline):
    model = BoardPost
    extra = 0
    fields = ["title", "author_persona", "created_at", "removed_at"]
    readonly_fields = ["created_at"]
    raw_id_fields = ["author_persona", "removed_by_persona"]


@admin.register(Board)
class BoardAdmin(admin.ModelAdmin):
    list_display = ["name", "room_profile", "organization", "max_active_posts", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["name"]
    raw_id_fields = ["room_profile", "organization"]
    inlines = [BoardPostInline]


@admin.register(BoardPost)
class BoardPostAdmin(admin.ModelAdmin):
    list_display = ["title", "board", "author_persona", "created_at", "removed_at"]
    list_filter = ["created_at", "removed_at"]
    search_fields = ["title", "body"]
    raw_id_fields = ["board", "author_persona", "removed_by_persona"]
    date_hierarchy = "created_at"
