"""
Character Creation admin configuration.

Note: SpeciesOrigin and SpeciesOriginStatBonus admin is in the species app
since they're permanent character data (lore), not CG-specific mechanics.
"""

from django.contrib import admin

from world.character_creation.models import (
    Beginnings,
    CharacterDraft,
    SpeciesOption,
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
    fieldsets = [
        (None, {"fields": ["realm", "name", "description", "crest_image"]}),
        (
            "Access Control",
            {"fields": ["is_active", "access_level", "minimum_trust", "sort_order"]},
        ),
        (
            "Game Integration",
            {
                "fields": ["default_starting_room"],
                "description": "Link to Evennia rooms.",
            },
        ),
    ]


@admin.register(Beginnings)
class BeginningsAdmin(admin.ModelAdmin):
    """Admin for Beginnings - worldbuilding paths in character creation."""

    list_display = [
        "name",
        "starting_area",
        "trust_required",
        "is_active",
        "allows_all_species",
        "family_known",
        "social_rank",
        "cg_point_cost",
        "sort_order",
    ]
    list_filter = ["starting_area", "is_active", "allows_all_species", "family_known"]
    search_fields = ["name", "description"]
    ordering = ["starting_area__name", "sort_order", "name"]
    filter_horizontal = ["species_options"]

    fieldsets = [
        (None, {"fields": ["name", "description", "art_image", "starting_area"]}),
        (
            "Access Control",
            {"fields": ["trust_required", "is_active", "sort_order"]},
        ),
        (
            "Character Creation Effects",
            {
                "fields": [
                    "allows_all_species",
                    "family_known",
                    "species_options",
                    "cg_point_cost",
                ],
            },
        ),
        (
            "Staff-Only",
            {
                "fields": ["social_rank"],
                "description": "Internal classification (not shown to players)",
            },
        ),
    ]


@admin.register(SpeciesOption)
class SpeciesOptionAdmin(admin.ModelAdmin):
    """Admin for SpeciesOption - CG costs and permissions for species origins."""

    list_display = [
        "species_origin",
        "starting_area",
        "trust_required",
        "is_available",
        "cg_point_cost",
        "language_count",
    ]
    list_filter = ["starting_area", "is_available", "trust_required"]
    search_fields = [
        "species_origin__name",
        "species_origin__species__name",
        "starting_area__name",
        "description_override",
    ]
    ordering = ["starting_area__name", "sort_order", "species_origin__name"]
    filter_horizontal = ["starting_languages"]

    fieldsets = [
        (None, {"fields": ["species_origin", "starting_area"]}),
        ("Access Control", {"fields": ["trust_required", "is_available"]}),
        ("Costs & Display", {"fields": ["cg_point_cost", "sort_order", "description_override"]}),
        ("Starting Languages", {"fields": ["starting_languages"]}),
    ]

    @admin.display(description="Languages")
    def language_count(self, obj):
        """Show count of starting languages."""
        return obj.starting_languages.count()


@admin.register(CharacterDraft)
class CharacterDraftAdmin(admin.ModelAdmin):
    list_display = [
        "__str__",
        "account",
        "current_stage",
        "selected_area",
        "selected_beginnings",
        "created_at",
        "updated_at",
    ]
    list_filter = ["current_stage", "selected_area", "selected_beginnings"]
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
                    "selected_beginnings",
                    "selected_species_option",
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
