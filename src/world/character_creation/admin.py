"""
Character Creation admin configuration.
"""

from django.contrib import admin

from world.character_creation.models import CharacterDraft, SpecialHeritage, StartingArea


@admin.register(StartingArea)
class StartingAreaAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "realm",
        "is_active",
        "access_level",
        "sort_order",
        "default_starting_room",
    ]
    list_filter = ["is_active", "access_level"]
    search_fields = ["name", "description"]
    ordering = ["sort_order", "name"]
    filter_horizontal = ["special_heritages"]
    fieldsets = [
        (None, {"fields": ["realm", "name", "description", "crest_image"]}),
        (
            "Access Control",
            {"fields": ["is_active", "access_level", "minimum_trust", "sort_order"]},
        ),
        (
            "Game Integration",
            {
                "fields": ["default_starting_room", "special_heritages"],
                "description": "Link to Evennia rooms and configure available heritages.",
            },
        ),
    ]


@admin.register(SpecialHeritage)
class SpecialHeritageAdmin(admin.ModelAdmin):
    list_display = [
        "heritage",
        "allows_full_species_list",
        "sort_order",
    ]
    list_select_related = ["heritage"]
    search_fields = ["heritage__name", "heritage__description"]
    ordering = ["sort_order"]
    fieldsets = [
        (None, {"fields": ["heritage", "sort_order"]}),
        (
            "Character Creation Effects",
            {
                "fields": [
                    "allows_full_species_list",
                    "starting_room_override",
                ],
            },
        ),
    ]


@admin.register(CharacterDraft)
class CharacterDraftAdmin(admin.ModelAdmin):
    list_display = [
        "__str__",
        "account",
        "current_stage",
        "selected_area",
        "created_at",
        "updated_at",
    ]
    list_filter = ["current_stage", "selected_area", "selected_heritage"]
    search_fields = ["account__username", "draft_data"]
    readonly_fields = ["created_at", "updated_at"]
    ordering = ["-updated_at"]
    fieldsets = [
        (None, {"fields": ["account", "current_stage"]}),
        (
            "Stage 1: Origin",
            {"fields": ["selected_area"]},
        ),
        (
            "Stage 2: Heritage",
            {
                "fields": [
                    "selected_heritage",
                    "selected_species",
                    "selected_gender",
                    "age",
                ],
            },
        ),
        (
            "Stage 3: Lineage",
            {"fields": ["family"]},
        ),
        (
            "Draft Data (JSON)",
            {
                "fields": ["draft_data"],
                "classes": ["collapse"],
            },
        ),
        (
            "Timestamps",
            {"fields": ["created_at", "updated_at"]},
        ),
    ]
