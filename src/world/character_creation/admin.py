"""
Character Creation admin configuration.
"""

from django import forms
from django.contrib import admin
from django.utils.html import format_html

from world.character_creation.constants import OfferArrival, OfferChapter
from world.character_creation.models import (
    AppearanceSection,
    BeginningEnemyOffer,
    Beginnings,
    BeginningTradition,
    CGExplanation,
    CGPointBudget,
    CharacterDraft,
    CharacterOriginSlot,
    DistinctionOffer,
    DraftApplication,
    DraftApplicationComment,
    DraftMarking,
    EnemyReason,
    LifeBeat,
    LifeBeatExclusion,
    OfferFirstLook,
    OriginTemplate,
    OriginTemplateSlot,
    OriginTemplateSlotChoice,
    SchoolingLine,
    StartingArea,
    TraditionStateLine,
)
from world.codex.admin import GrantReachOnSaveMixin
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


class BeatExclusionForBeginningInline(admin.TabularInline):
    """The library beats this Beginning never meets (#4124); the rest apply."""

    model = LifeBeatExclusion
    extra = 0
    autocomplete_fields = ["beat"]
    fields = ["beat", "reason"]


@admin.register(Beginnings)
class BeginningsAdmin(GrantReachOnSaveMixin, admin.ModelAdmin):
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
    inlines = [
        BeginningTraditionInline,
        BeginningsCodexGrantInline,
        BeginningEnemyOfferInline,
        BeatExclusionForBeginningInline,
    ]

    fieldsets = [
        (None, {"fields": ["name", "description", "art", "starting_area"]}),
        (
            "Access Control",
            {"fields": ["is_active", "sort_order"]},
        ),
        (
            "Species Selection",
            {
                "fields": ["allowed_species", "cg_point_cost", "beat_mode"],
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
    # The kind is shown, not edited, here: a pick, group or person question
    # carries answers and anchors that only the Upbringing builder edits (#4037).
    fields = ["name", "kind", "prompt", "applies_to", "allows_text", "is_required", "sort_order"]
    readonly_fields = ["kind"]


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
        "parentage",
        "is_active",
        "sort_order",
        "builder_link",
    ]
    list_filter = ["is_active", "parentage", "beginning__starting_area"]
    search_fields = ["name", "frame_narrative", "parentage_note"]
    ordering = ["beginning", "sort_order", "name"]
    filter_horizontal = ["claimable_kinds", "family_templates"]
    inlines = [OriginTemplateSlotInline]

    @admin.display(description="Builder")
    def builder_link(self, obj: OriginTemplate) -> str:
        """Each row's way into the Upbringing builder, where question kinds,
        answers and their distinction offers are edited (#4037)."""
        from web.admin.authoring.links import builder_url  # noqa: PLC0415

        return format_html('<a href="{}">Open in builder</a>', builder_url(obj))


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


class BeatAnswerForm(forms.ModelForm):
    """An answer row on the beat admin (#4124): the chapter and arrival are not the
    operator's to pick, so the form fixes them before the model's own clean runs."""

    class Meta:
        model = DistinctionOffer
        fields = ["distinction", "name", "player_line", "sort_order", "is_active"]

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.instance.chapter = OfferChapter.BACKGROUNDS
        self.instance.arrives_as = OfferArrival.CHOICE


class BeatAnswerInline(admin.TabularInline):
    """A beat's answers (#4124): one ``DistinctionOffer`` per answer, every one a priced
    choice in the Backgrounds chapter. The chapter and arrival are fixed on save."""

    model = DistinctionOffer
    form = BeatAnswerForm
    fk_name = "beat"
    extra = 1
    autocomplete_fields = ["distinction"]
    fields = ["distinction", "name", "player_line", "sort_order", "is_active"]
    verbose_name = "Answer"
    verbose_name_plural = "Answers"


class BeatExclusionInline(admin.TabularInline):
    """The Beginnings that never meet this beat (#4124); every other Beginning does."""

    model = LifeBeatExclusion
    extra = 0
    autocomplete_fields = ["beginning"]
    fields = ["beginning", "reason"]


@admin.register(LifeBeat)
class LifeBeatAdmin(admin.ModelAdmin):
    """The Backgrounds beat library (#4124): one row per beat, authored once for every
    Beginning; its answers and its exclusions sit inline."""

    list_display = ["name", "life_stage", "selection", "sort_order", "is_active"]
    list_filter = ["life_stage", "selection", "is_active"]
    search_fields = ["name", "prompt"]
    ordering = ["life_stage", "sort_order", "name"]
    inlines = [BeatAnswerInline, BeatExclusionInline]
    fieldsets = [
        (None, {"fields": ["name", "life_stage", "prompt", "selection"]}),
        ("Listing", {"fields": ["sort_order", "is_active"]}),
        CREDIT_FIELDSET,
    ]

    def save_formset(self, request, form, formset, change):
        """An answer is always a Backgrounds choice opened by this beat; every saved row is
        credited to the operator, mirroring the Glimpse tag admin (#3675)."""
        if formset.model is not DistinctionOffer:
            super().save_formset(request, form, formset, change)
            return
        from web.admin.authoring.contributors import current_contributor  # noqa: PLC0415
        from web.admin.authoring.credit import stamp_written  # noqa: PLC0415

        instances = formset.save(commit=False)
        for obj in formset.deleted_objects:
            obj.delete()
        contributor = current_contributor(request.user)
        for obj in instances:
            obj.chapter = OfferChapter.BACKGROUNDS
            obj.arrives_as = OfferArrival.CHOICE
            obj.beat = form.instance
            obj.save()
            if contributor is not None:
                stamp_written(obj, contributor)
        formset.save_m2m()


@admin.register(CharacterOriginSlot)
class CharacterOriginSlotAdmin(admin.ModelAdmin):
    """Read-only admin for character origin-slot answers and beat rows (#2478, #4124)."""

    list_display = [
        "sheet",
        "slot",
        "beat",
        "unknown",
        "organization",
        "figure_name",
        "choice",
        "value",
    ]
    list_filter = [
        "slot__template__beginning__starting_area",
        "slot__kind",
        "beat__life_stage",
        "unknown",
        "organization",
    ]
    search_fields = ["value", "figure_name", "organization__name", "beat__name"]
    readonly_fields = ["sheet", "slot", "beat", "value", "choice", "organization", "figure_name"]
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


# ---------------------------------------------------------------------------
# #3831
# ---------------------------------------------------------------------------


@admin.register(CGPointBudget)
class CGPointBudgetAdmin(admin.ModelAdmin):
    """#3831 - the CG point budget configuration (staff-tunable, no code change)."""

    list_display = ["name", "starting_points", "xp_conversion_rate", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name"]


@admin.register(OfferFirstLook)
class OfferFirstLookAdmin(admin.ModelAdmin):
    """#3831 - one Beginning pinning one offer line into its chapter's first look."""

    list_display = ["beginning", "offer"]
    list_select_related = ["beginning"]
    raw_id_fields = ["offer"]
    autocomplete_fields = ["beginning"]
    search_fields = ["beginning__name"]


@admin.register(TraditionStateLine)
class TraditionStateLineAdmin(admin.ModelAdmin):
    """#3831 - the standard words + drawback for one tradition state (#3675).

    Normally authored on the Tradition Slate admin page
    (``web/admin/tradition_slate/``); this standalone page is the fallback
    editor for a one-off correction.
    """

    list_display = ["state", "entry_line", "carries"]
    list_select_related = ["carries"]
    autocomplete_fields = ["carries"]
    search_fields = ["entry_line"]


@admin.register(SchoolingLine)
class SchoolingLineAdmin(admin.ModelAdmin):
    """#3831 - one line of the standard schooling set under a living tradition (#3675).

    Normally authored on the Tradition Slate admin page
    (``web/admin/tradition_slate/``); this standalone page is the fallback
    editor for a one-off correction.
    """

    list_display = ["rank", "name", "player_line", "grants"]
    list_select_related = ["grants"]
    autocomplete_fields = ["grants"]
    search_fields = ["name", "player_line"]
