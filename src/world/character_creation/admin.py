"""
Character Creation admin configuration.
"""

from django.contrib import admin

from world.character_creation.models import (
    CharacterDraft,
    SpecialHeritage,
    SpeciesArea,
    SpeciesAreaStatBonus,
    StartingArea,
)


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


class SpeciesAreaStatBonusInline(admin.TabularInline):
    """Inline for stat bonuses on SpeciesArea."""

    model = SpeciesAreaStatBonus
    extra = 1
    fields = ["stat", "value"]


@admin.register(SpeciesArea)
class SpeciesAreaAdmin(admin.ModelAdmin):
    """Admin for SpeciesArea through model."""

    list_display = [
        "species",
        "starting_area",
        "trust_required",
        "is_available",
        "cg_point_cost",
        "language_count",
    ]
    list_filter = ["starting_area", "is_available", "trust_required"]
    search_fields = ["species__name", "starting_area__name", "description_override"]
    ordering = ["starting_area__name", "sort_order", "species__name"]
    filter_horizontal = ["starting_languages"]
    inlines = [SpeciesAreaStatBonusInline]

    fieldsets = [
        (None, {"fields": ["species", "starting_area"]}),
        ("Access Control", {"fields": ["trust_required", "is_available"]}),
        ("Costs & Display", {"fields": ["cg_point_cost", "sort_order", "description_override"]}),
        ("Starting Languages", {"fields": ["starting_languages"]}),
    ]

    @admin.display(description="Languages")
    def language_count(self, obj):
        """Show count of starting languages."""
        return obj.starting_languages.count()


@admin.register(SpeciesAreaStatBonus)
class SpeciesAreaStatBonusAdmin(admin.ModelAdmin):
    """Admin for SpeciesAreaStatBonus (mainly for debugging)."""

    list_display = ["species_area", "stat", "value"]
    list_filter = ["stat", "species_area__starting_area"]
    search_fields = ["species_area__species__name"]


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
                    "selected_species_area",
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
