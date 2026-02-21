"""
Character Creation admin configuration.
"""

from django.contrib import admin

from world.character_creation.models import (
    Beginnings,
    BeginningTradition,
    CGExplanations,
    CharacterDraft,
    DraftApplication,
    DraftApplicationComment,
    StartingArea,
    TraditionTemplate,
    TraditionTemplateFacet,
    TraditionTemplateTechnique,
)
from world.codex.models import BeginningsCodexGrant


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
        (None, {"fields": ["name", "description", "art_image", "starting_area"]}),
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


@admin.register(CharacterDraft)
class CharacterDraftAdmin(admin.ModelAdmin):
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
    list_display = ["__str__", "status", "submitted_at", "reviewer", "reviewed_at", "expires_at"]
    list_filter = ["status"]
    search_fields = ["draft__account__username", "draft__draft_data"]
    readonly_fields = ["submitted_at"]
    inlines = [DraftApplicationCommentInline]


class TraditionTemplateTechniqueInline(admin.TabularInline):
    model = TraditionTemplateTechnique
    extra = 1
    raw_id_fields = ["style", "effect_type"]


class TraditionTemplateFacetInline(admin.TabularInline):
    model = TraditionTemplateFacet
    extra = 1
    raw_id_fields = ["resonance", "facet"]


@admin.register(TraditionTemplate)
class TraditionTemplateAdmin(admin.ModelAdmin):
    list_display = ["tradition", "path", "gift_name"]
    list_filter = ["tradition", "path"]
    search_fields = ["gift_name", "tradition__name", "path__name"]
    raw_id_fields = [
        "tradition",
        "path",
        "anima_ritual_stat",
        "anima_ritual_skill",
        "anima_ritual_resonance",
    ]
    filter_horizontal = ["resonances"]
    inlines = [TraditionTemplateTechniqueInline, TraditionTemplateFacetInline]


@admin.register(CGExplanations)
class CGExplanationsAdmin(admin.ModelAdmin):
    fieldsets = [
        (
            "Origin",
            {"fields": ["origin_heading", "origin_intro"]},
        ),
        (
            "Heritage",
            {
                "fields": [
                    "heritage_heading",
                    "heritage_intro",
                    "heritage_beginnings_heading",
                    "heritage_beginnings_desc",
                    "heritage_species_heading",
                    "heritage_species_desc",
                    "heritage_gender_heading",
                    "heritage_cg_points_explanation",
                ],
            },
        ),
        (
            "Lineage",
            {"fields": ["lineage_heading", "lineage_intro"]},
        ),
        (
            "Distinctions",
            {
                "fields": [
                    "distinctions_heading",
                    "distinctions_intro",
                    "distinctions_budget_explanation",
                ],
            },
        ),
        (
            "Path & Skills",
            {
                "fields": [
                    "path_heading",
                    "path_intro",
                    "path_skills_heading",
                    "path_skills_desc",
                ],
            },
        ),
        (
            "Attributes",
            {
                "fields": [
                    "attributes_heading",
                    "attributes_intro",
                    "attributes_bonus_explanation",
                ],
            },
        ),
        (
            "Magic",
            {
                "fields": [
                    "magic_heading",
                    "magic_intro",
                    "magic_gift_heading",
                    "magic_gift_desc",
                    "magic_anima_heading",
                    "magic_anima_desc",
                    "magic_motif_heading",
                    "magic_motif_desc",
                    "magic_glimpse_heading",
                    "magic_glimpse_desc",
                ],
            },
        ),
        (
            "Appearance",
            {"fields": ["appearance_heading", "appearance_intro"]},
        ),
        (
            "Identity",
            {"fields": ["identity_heading", "identity_intro"]},
        ),
        (
            "Final Touches",
            {"fields": ["finaltouches_heading", "finaltouches_intro"]},
        ),
        (
            "Review",
            {
                "fields": [
                    "review_heading",
                    "review_intro",
                    "review_xp_explanation",
                ],
            },
        ),
    ]

    def has_add_permission(self, _request):
        return not CGExplanations.objects.exists()

    def has_delete_permission(self, _request, _obj=None):
        return False
