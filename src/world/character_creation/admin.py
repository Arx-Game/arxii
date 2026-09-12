"""
Character Creation admin configuration.
"""

from django.contrib import admin

from world.character_creation.models import (
    AppearanceSection,
    BeginningEnemyOffer,
    Beginnings,
    BeginningTradition,
    CGExplanation,
    CharacterDraft,
    CharacterOriginSlot,
    DraftApplication,
    DraftApplicationComment,
    DraftMarking,
    EnemyReason,
    OriginTemplate,
    OriginTemplateSlot,
    OriginTemplateSlotChoice,
    StartingArea,
)
from world.codex.models import BeginningsCodexGrant
from world.contributors.admin import CREDIT_FIELDSET


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
    fieldsets = [
        (None, {"fields": ["realm", "name", "description", "crest_art"]}),
        (
            "Access Control",
            {"fields": ["is_active", "access_level", "sort_order"]},
        ),
        (
            "Game Integration",
            {
                "fields": ["default_starting_room"],
                "description": "Link to Evennia rooms.",
            },
        ),
        CREDIT_FIELDSET,
    ]


class BeginningsCodexGrantInline(admin.TabularInline):
    model = BeginningsCodexGrant
    extra = 1
    autocomplete_fields = ["entry"]


class BeginningTraditionInline(admin.TabularInline):
    model = BeginningTradition
    extra = 1
    raw_id_fields = ["tradition"]


class BeginningEnemyOfferInline(admin.TabularInline):
    """What the Beginning itself puts in the character's way (#3621)."""

    model = BeginningEnemyOffer
    extra = 0
    raw_id_fields = ["organization"]
    autocomplete_fields = ["reason"]
    fields = [
        "organization",
        "figure_name",
        "power_tier",
        "reach_override",
        "reason",
        "why",
        "sort_order",
    ]


@admin.register(Beginnings)
class BeginningsAdmin(admin.ModelAdmin):
    """Admin for Beginnings - worldbuilding paths in character creation."""

    autocomplete_fields = ["starting_room_override", "art"]

    list_display = [
        "name",
        "starting_area",
        "is_active",
        "grants_species_languages",
        "species_count",
        "social_rank",
        "cg_point_cost",
        "sort_order",
    ]
    list_filter = [
        "starting_area",
        "is_active",
        "grants_species_languages",
    ]
    search_fields = ["name", "description"]
    ordering = ["starting_area__name", "sort_order", "name"]
    filter_horizontal = ["allowed_species", "starting_languages"]
    inlines = [BeginningTraditionInline, BeginningsCodexGrantInline, BeginningEnemyOfferInline]

    fieldsets = [
        (None, {"fields": ["name", "description", "art", "starting_area"]}),
        (
            "Access Control",
            {"fields": ["is_active", "sort_order"]},
        ),
        (
            "Species Selection",
            {
                "fields": ["allowed_species", "cg_point_cost"],
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
        CREDIT_FIELDSET,
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
    show_change_link = True
    fields = ["name", "prompt", "applies_to", "allows_text", "is_required", "sort_order"]


@admin.register(OriginTemplate)
class OriginTemplateAdmin(admin.ModelAdmin):
    """Admin for Upbringings (#2478, #3617)."""

    list_display = [
        "name",
        "beginning",
        "cg_point_cost",
        "allows_claim_family",
        "allows_name_family",
        "allows_no_family",
        "is_active",
        "sort_order",
    ]
    list_filter = ["is_active", "beginning__starting_area"]
    search_fields = ["name", "frame_narrative"]
    ordering = ["beginning", "sort_order", "name"]
    filter_horizontal = ["claimable_kinds", "family_templates"]
    inlines = [OriginTemplateSlotInline]


class OriginTemplateSlotChoiceInline(admin.TabularInline):
    model = OriginTemplateSlotChoice
    extra = 1
    ordering = ["sort_order"]


@admin.register(OriginTemplateSlot)
class OriginTemplateSlotAdmin(admin.ModelAdmin):
    """Prompts get their own page so their choices can be edited inline (#3617)."""

    list_display = ["name", "template", "applies_to", "allows_text", "is_required", "sort_order"]
    list_filter = ["applies_to", "template__beginning__starting_area"]
    search_fields = ["name", "prompt"]
    inlines = [OriginTemplateSlotChoiceInline]


@admin.register(OriginTemplateSlotChoice)
class OriginTemplateSlotChoiceAdmin(admin.ModelAdmin):
    """Standalone registration so autocomplete widgets elsewhere can search it (#3675).

    Otherwise this model is only reachable through
    ``OriginTemplateSlotChoiceInline`` above - the Distinction Builder's
    ``origin_choice`` autocomplete needs a plain ``ModelAdmin`` with its own
    ``search_fields`` (Django's autocomplete view 404s without one).
    """

    list_display = ["name", "slot", "cg_point_cost", "is_active"]
    list_filter = ["is_active", "slot__template"]
    search_fields = ["name", "slot__name", "slot__template__name"]
    autocomplete_fields = ["slot"]


@admin.register(CharacterOriginSlot)
class CharacterOriginSlotAdmin(admin.ModelAdmin):
    """Read-only admin for character origin-slot answers (#2478)."""

    list_display = ["sheet", "slot", "organization", "figure_name", "choice", "value"]
    list_filter = ["slot__template__beginning__starting_area", "slot__kind", "organization"]
    search_fields = ["value", "figure_name", "organization__name"]
    readonly_fields = ["sheet", "slot", "value", "choice", "organization", "figure_name"]
    autocomplete_fields = ["sheet"]


class DraftMarkingInline(admin.TabularInline):
    model = DraftMarking
    extra = 0


@admin.register(CharacterDraft)
class CharacterDraftAdmin(admin.ModelAdmin):
    autocomplete_fields = ["account"]
    inlines = [DraftMarkingInline]
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


@admin.register(EnemyReason)
class EnemyReasonAdmin(admin.ModelAdmin):
    """The shared list of why an enemy wants the character to fail (#3709).

    A plain change list: written once for the whole game, filtered by ``fits`` on the
    leaf, pinned per Beginning enemy offer, and the enemy chapter's opener on the
    Distinction Builder (its ``enemy_reason`` autocomplete needs ``search_fields``).
    """

    list_display = ["name", "player_line", "fits", "offers", "sort_order", "is_active"]
    list_filter = ["fits", "is_active"]
    search_fields = ["name", "player_line"]
    fieldsets = [
        (None, {"fields": ("name", "player_line", "fits", "sort_order", "is_active")}),
        CREDIT_FIELDSET,
    ]

    @admin.display(description="Offers")
    def offers(self, obj: EnemyReason) -> int:
        return obj.distinction_offers.count()


@admin.register(AppearanceSection)
class AppearanceSectionAdmin(admin.ModelAdmin):
    """The headings the Appearance chapter groups its offers under (#3709)."""

    list_display = ["name", "player_line", "sort_order"]
    search_fields = ["name"]
    fieldsets = [
        (None, {"fields": ("name", "player_line", "sort_order")}),
        CREDIT_FIELDSET,
    ]
