"""
Character Creation admin configuration.
"""

from django.contrib import admin

from world.character_creation.models import (
    Beginnings,
    BeginningTradition,
    CGExplanation,
    CharacterDraft,
    CharacterOriginSlot,
    DraftApplication,
    DraftApplicationComment,
    OriginTemplate,
    OriginTemplateSlot,
    StartingArea,
)
from world.codex.models import BeginningsCodexGrant


@admin.register(StartingArea)
class StartingAreaAdmin(admin.ModelAdmin):
    autocomplete_fields = ["default_starting_room", "crest_art"]
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
    raw_id_fields = ["default_starting_room"]
    fieldsets = [
        (None, {"fields": ["realm", "name", "description", "crest_art"]}),
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


class BeginningsCodexGrantInline(admin.TabularInline):
    model = BeginningsCodexGrant
    extra = 1
    autocomplete_fields = ["entry"]


class BeginningTraditionInline(admin.TabularInline):
    model = BeginningTradition
    extra = 1
    raw_id_fields = ["tradition", "required_distinction"]


@admin.register(Beginnings)
class BeginningsAdmin(admin.ModelAdmin):
    """Admin for Beginnings - worldbuilding paths in character creation."""

    autocomplete_fields = ["starting_room_override", "art"]

    list_display = [
        "name",
        "starting_area",
        "trust_required",
        "is_active",
        "family_known",
        "grants_species_languages",
        "species_count",
        "social_rank",
        "cg_point_cost",
        "sort_order",
    ]
    list_filter = [
        "starting_area",
        "is_active",
        "family_known",
        "grants_species_languages",
    ]
    search_fields = ["name", "description"]
    ordering = ["starting_area__name", "sort_order", "name"]
    filter_horizontal = ["allowed_species", "starting_languages"]
    inlines = [BeginningTraditionInline, BeginningsCodexGrantInline]

    fieldsets = [
        (None, {"fields": ["name", "description", "art", "starting_area"]}),
        (
            "Access Control",
            {"fields": ["trust_required", "is_active", "sort_order"]},
        ),
        (
            "Species Selection",
            {
                "fields": ["allowed_species", "family_known", "cg_point_cost"],
                "description": "Select species (parent species include all subtypes)",
            },
        ),
        (
            "Languages",
            {
                "fields": ["starting_languages", "grants_species_languages"],
                "description": "Languages granted; uncheck for Misbegotten",
            },
        ),
        (
            "Staff-Only",
            {
                "fields": ["social_rank", "starting_room_override"],
                "description": "Internal classification and room override",
            },
        ),
    ]

    @admin.display(description="Species")
    def species_count(self, obj):
        """Show count of allowed species."""
        return obj.allowed_species.count()


class OriginTemplateSlotInline(admin.TabularInline):
    """Inline for slot prompts within an origin template (#2478)."""

    model = OriginTemplateSlot
    extra = 1
    ordering = ["sort_order"]


@admin.register(OriginTemplate)
class OriginTemplateAdmin(admin.ModelAdmin):
    """Admin for origin-story templates (#2478)."""

    list_display = ["name", "beginning", "is_active", "sort_order"]
    list_filter = ["is_active", "beginning__starting_area"]
    search_fields = ["name", "frame_narrative"]
    ordering = ["beginning", "sort_order", "name"]
    inlines = [OriginTemplateSlotInline]


@admin.register(CharacterOriginSlot)
class CharacterOriginSlotAdmin(admin.ModelAdmin):
    """Read-only admin for character origin-slot answers (#2478)."""

    list_display = ["sheet", "slot", "value"]
    list_filter = ["slot__template__beginning__starting_area"]
    search_fields = ["value"]
    readonly_fields = ["sheet", "slot", "value"]
    autocomplete_fields = ["sheet"]


@admin.register(CharacterDraft)
class CharacterDraftAdmin(admin.ModelAdmin):
    autocomplete_fields = ["account"]
    list_display = [
        "__str__",
        "account",
        "current_stage",
        "selected_area",
        "selected_beginnings",
        "selected_species",
        "created_at",
        "updated_at",
    ]
    list_filter = ["current_stage", "selected_area", "selected_beginnings", "selected_species"]
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
            "Path & Tradition",
            {"fields": ["selected_path", "selected_tradition"]},
        ),
        (
            "Appearance",
            {"fields": ["height_band", "height_inches", "build"]},
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


class DraftApplicationCommentInline(admin.TabularInline):
    model = DraftApplicationComment
    extra = 0
    readonly_fields = ["author", "text", "comment_type", "created_at"]


@admin.register(DraftApplication)
class DraftApplicationAdmin(admin.ModelAdmin):
    autocomplete_fields = ["player_account", "reviewer"]
    list_display = ["__str__", "status", "submitted_at", "reviewer", "reviewed_at", "expires_at"]
    list_filter = ["status"]
    search_fields = ["draft__account__username", "draft__draft_data"]
    readonly_fields = ["submitted_at"]
    inlines = [DraftApplicationCommentInline]


@admin.register(CGExplanation)
class CGExplanationAdmin(admin.ModelAdmin):
    list_display = ["key", "truncated_text", "help_text"]
    list_editable = ["help_text"]
    search_fields = ["key", "text", "help_text"]
    ordering = ["key"]

    @admin.display(description="Text")
    def truncated_text(self, obj):
        truncate_at = 80
        if len(obj.text) > truncate_at:
            return obj.text[:truncate_at] + "..."
        return obj.text
