"""Django admin configuration for the codex system."""

from django.contrib import admin, messages
from django.db.models import Count, Q
from django.http import HttpRequest

from world.clues.models import Clue
from world.codex.models import (
    BeginningsCodexGrant,
    CharacterCodexKnowledge,
    CodexCategory,
    CodexEntry,
    CodexEntryFiling,
    CodexSubject,
    CodexTeachingOffer,
    DistinctionCodexGrant,
    OrganizationCodexGrant,
    PathCodexGrant,
    TraditionCodexGrant,
)
from world.codex.services import grant_entry_to_species_holders, grant_to_current_holders
from world.contributors.admin import CREDIT_FIELDSET


class CodexSubjectInline(admin.TabularInline):
    """Inline admin for subjects within a category."""

    model = CodexSubject
    extra = 0
    fields = ["name", "parent", "display_order"]
    fk_name = "category"


@admin.register(CodexCategory)
class CodexCategoryAdmin(admin.ModelAdmin):
    """Admin interface for CodexCategory."""

    list_display = ["name", "subject_count", "display_order"]
    search_fields = ["name"]
    ordering = ["display_order", "name"]
    inlines = [CodexSubjectInline]

    def subject_count(self, obj: CodexCategory) -> int:
        return obj.subjects.count()

    subject_count.short_description = "Subjects"


class CodexEntryInline(admin.TabularInline):
    """Inline admin for entries within a subject."""

    model = CodexEntry
    extra = 0
    fields = ["name", "share_cost", "learn_cost", "display_order"]


@admin.register(CodexSubject)
class CodexSubjectAdmin(admin.ModelAdmin):
    """Admin interface for CodexSubject."""

    list_display = ["name", "category", "parent", "entry_count", "display_order"]
    list_filter = ["category"]
    search_fields = ["name", "category__name"]
    ordering = ["category", "display_order", "name"]
    inlines = [CodexEntryInline]

    def entry_count(self, obj: CodexSubject) -> int:
        return obj.entries.count()

    entry_count.short_description = "Entries"


class CodexEntryFilingInline(admin.TabularInline):
    """Inline admin for an entry's secondary listings under other subjects."""

    model = CodexEntryFiling
    extra = 0
    fields = ["subject", "sort_order"]
    autocomplete_fields = ["subject"]


class GrantReachOnSaveMixin:
    """Apply newly created grant inline rows to the characters already in the group.

    Every admin that can create a grant row (the entry, Beginnings, Tradition,
    Path, Distinction and Organization grant admins) mixes this in, so a grant
    added after characters exist is never a dead row (#3775). Runs after the
    inline formsets save, reads each formset's ``new_objects``, and only acts on
    rows whose model has ``holder_roster_entries``.
    """

    def save_related(self, request: HttpRequest, form, formsets, change: bool) -> None:
        super().save_related(request, form, formsets, change)  # type: ignore[misc]
        learned = 0
        rows = 0
        for formset in formsets:
            # save_new_objects (called above, inside super().save_related()) always
            # sets this on a BaseModelFormSet before returning.
            for grant in formset.new_objects:
                if hasattr(grant, "holder_roster_entries"):
                    learned += grant_to_current_holders(grant)
                    rows += 1
        if rows:
            messages.info(
                request,
                f"{rows} new grant row(s) reached {learned} existing character(s).",
            )


#: string literals, per tools/lint_string_literal.py.
_REACH_PUBLIC = "public"
_REACH_GRANTED = "granted"
_REACH_CLUE = "clue"
_REACH_UNREACHABLE = "unreachable"


class ReachListFilter(admin.SimpleListFilter):
    """How an entry can be reached: public, granted to a group, by a clue, or not at all."""

    title = "reach"
    parameter_name = "reach"

    #: Django passes both hook arguments positionally, so the leading underscores
    #: mark them unused without needing a suppression.
    def lookups(self, _request, _model_admin):
        return [
            (_REACH_PUBLIC, "Public"),
            (_REACH_GRANTED, "Granted to a group"),
            (_REACH_CLUE, "Reached by a clue"),
            (_REACH_UNREACHABLE, "Unreachable"),
        ]

    def queryset(self, _request, queryset):
        granted = (
            Q(beginnings_grants__isnull=False)
            | Q(tradition_grants__isnull=False)
            | Q(path_grants__isnull=False)
            | Q(distinction_grants__isnull=False)
            | Q(organization_grants__isnull=False)
            | Q(species__isnull=False)
        )
        if self.value() == _REACH_PUBLIC:
            return queryset.filter(is_public=True)
        if self.value() == _REACH_GRANTED:
            return queryset.filter(granted).distinct()
        if self.value() == _REACH_CLUE:
            return queryset.filter(clues__isnull=False).distinct()
        if self.value() == _REACH_UNREACHABLE:
            return queryset.filter(is_public=False).exclude(granted).exclude(clues__isnull=False)
        return queryset


class _GrantInline(admin.TabularInline):
    """Base for a codex grant inline: shows how many characters hold it today."""

    extra = 0
    readonly_fields = ["holders_today"]

    @admin.display(description="Holders today")
    def holders_today(self, obj) -> str:
        if obj.pk is None:
            return ""
        return f"{len(obj.holder_roster_entries())} characters"


class BeginningsGrantInline(_GrantInline):
    """Codex entries granted by a Beginnings choice."""

    model = BeginningsCodexGrant
    fields = ["beginnings", "is_perspective", "holders_today"]
    autocomplete_fields = ["beginnings"]
    verbose_name_plural = "Known from birth: Beginnings codex grants"


class TraditionGrantInline(_GrantInline):
    """Codex entries granted by a Tradition."""

    model = TraditionCodexGrant
    fields = ["tradition", "is_perspective", "holders_today"]
    autocomplete_fields = ["tradition"]
    verbose_name_plural = "Taught by a tradition: Tradition codex grants"


class OrganizationGrantInline(_GrantInline):
    """Codex entries granted to an Organization's membership on joining."""

    model = OrganizationCodexGrant
    fields = ["organization", "holders_today"]
    autocomplete_fields = ["organization"]
    verbose_name_plural = "Taught on joining: Organization codex grants"


class PathGrantInline(_GrantInline):
    """Codex entries granted by a Path choice."""

    model = PathCodexGrant
    fields = ["path", "holders_today"]
    autocomplete_fields = ["path"]
    verbose_name_plural = "Path codex grants"


class DistinctionGrantInline(_GrantInline):
    """Codex entries granted by a Distinction."""

    model = DistinctionCodexGrant
    fields = ["distinction", "holders_today"]
    autocomplete_fields = ["distinction"]
    verbose_name_plural = "Distinction codex grants"


class ClueInline(admin.TabularInline):
    """Read only: the clues that lead to this entry. Author them under Clues."""

    model = Clue
    fk_name = "target_codex_entry"
    fields = ["slug", "target_kind"]
    readonly_fields = ["slug", "target_kind"]
    extra = 0
    can_delete = False
    verbose_name_plural = "Found through a Mystery: clues leading here (read only)"

    def has_add_permission(self, request, obj=None) -> bool:  # noqa: ARG002
        return False

    def has_change_permission(self, request, obj=None) -> bool:  # noqa: ARG002
        return False


@admin.register(CodexEntry)
class CodexEntryAdmin(GrantReachOnSaveMixin, admin.ModelAdmin):
    """Admin interface for CodexEntry: leads with who knows it (#3775)."""

    inlines = [
        CodexEntryFilingInline,
        BeginningsGrantInline,
        TraditionGrantInline,
        OrganizationGrantInline,
        PathGrantInline,
        DistinctionGrantInline,
        ClueInline,
    ]
    list_display = ["name", "subject", "is_public", "known_via", "prerequisite_count"]
    list_filter = [ReachListFilter, "is_public", "subject__category", "subject"]
    search_fields = ["name", "subject__name", "lore_content", "mechanics_content"]
    filter_horizontal = ["prerequisites"]
    ordering = ["subject", "display_order", "name"]
    actions = ["publish_entries", "unpublish_entries", "grant_to_holders"]
    autocomplete_fields = ["modifier_target", "art", "subject_item_instance"]

    fieldsets = (
        (None, {"fields": ("subject", "name", "summary", "quote", "art")}),
        (
            "Content",
            {
                "fields": ("lore_content", "mechanics_content"),
                "description": "At least one content field (lore or mechanics) is required.",
            },
        ),
        (
            "Who knows this",
            {
                "fields": ("is_public", "is_featured", "featured_order"),
                "description": (
                    "Public: everyone can read it, including visitors who are not logged in. "
                    "Leave it off when a character has to get it by a path: born into it, "
                    "taught by a tradition, taught on joining an organization, taught by "
                    "another character, or found through a Mystery. The grant tables below "
                    "are those paths. An entry a clue leads to cannot be public."
                ),
            },
        ),
        (
            "Costs and learning",
            {
                "fields": ("share_cost", "learn_cost", "learn_difficulty", "learn_threshold"),
                "description": "AP to teach and accept; difficulty and progress for research.",
                "classes": ["collapse"],
            },
        ),
        ("Prerequisites", {"fields": ("prerequisites",), "classes": ["collapse"]}),
        (
            "Mechanics link",
            {
                "fields": ("modifier_target",),
                "description": (
                    "Link to a modifier target (resonance, stat, etc.) this entry documents."
                ),
                "classes": ["collapse"],
            },
        ),
        (
            "Item pointer",
            {
                "fields": ("subject_item_template", "subject_item_instance"),
                "description": "Optional: this entry is about an item kind/instance (#2540).",
                "classes": ["collapse"],
            },
        ),
        ("Display order", {"fields": ("display_order",), "classes": ["collapse"]}),
        CREDIT_FIELDSET,
    )

    def get_queryset(self, request: HttpRequest):
        return (
            super()
            .get_queryset(request)
            .select_related("subject")
            .annotate(
                beginnings_count=Count("beginnings_grants", distinct=True),
                tradition_count=Count("tradition_grants", distinct=True),
                organization_count=Count("organization_grants", distinct=True),
                path_count=Count("path_grants", distinct=True),
                distinction_count=Count("distinction_grants", distinct=True),
                species_count=Count("species", distinct=True),
                clue_count=Count("clues", distinct=True),
            )
        )

    @admin.display(description="Known via")
    def known_via(self, obj: CodexEntry) -> str:
        parts = []
        for count, label in (
            (obj.beginnings_count, "beginnings"),
            (obj.tradition_count, "tradition"),
            (obj.organization_count, "organization"),
            (obj.path_count, "path"),
            (obj.distinction_count, "distinction"),
            (obj.species_count, "species"),
            (obj.clue_count, "clue"),
        ):
            if count:
                parts.append(f"{count} {label}")
        if not parts:
            return "public only" if obj.is_public else "unreachable"
        return ", ".join(parts)

    @admin.display(description="Prerequisites")
    def prerequisite_count(self, obj: CodexEntry) -> int:
        return obj.prerequisites.count()

    @admin.action(description="Publish (everyone can read)")
    def publish_entries(self, request: HttpRequest, queryset) -> None:
        skipped = []
        flipped = 0
        for entry in queryset:
            if entry.clues.exists():
                skipped.append(entry.name)
                continue
            if not entry.is_public:
                entry.is_public = True
                entry.save(update_fields=["is_public"])
                flipped += 1
        messages.success(request, f"Published {flipped} entries.")
        if skipped:
            messages.warning(
                request,
                "Skipped, a clue leads to them: " + ", ".join(sorted(skipped)),
            )

    @admin.action(description="Unpublish")
    def unpublish_entries(self, request: HttpRequest, queryset) -> None:
        flipped = 0
        unfeatured = 0
        for entry in queryset:
            if not entry.is_public:
                continue
            fields = ["is_public"]
            entry.is_public = False
            if entry.is_featured or entry.featured_order is not None:
                entry.is_featured = False
                entry.featured_order = None
                fields += ["is_featured", "featured_order"]
                unfeatured += 1
            entry.save(update_fields=fields)
            flipped += 1
        messages.success(
            request, f"Unpublished {flipped} entries; {unfeatured} were also un-featured."
        )

    @admin.action(description="Grant to current holders")
    def grant_to_holders(self, request: HttpRequest, queryset) -> None:
        checked = 0
        learned = 0
        unreachable = 0
        for entry in queryset:
            checked += 1
            grants = [
                *entry.beginnings_grants.all(),
                *entry.tradition_grants.all(),
                *entry.organization_grants.all(),
                *entry.path_grants.all(),
                *entry.distinction_grants.all(),
            ]
            for grant in grants:
                learned += grant_to_current_holders(grant)
            learned += grant_entry_to_species_holders(entry)
            if (
                not grants
                and not entry.is_public
                and not entry.clues.exists()
                and not entry.species.exists()
            ):
                unreachable += 1
        messages.success(
            request,
            f"{checked} entries checked; {learned} knowledge rows created; "
            f"{unreachable} entries still unreachable.",
        )


@admin.register(CharacterCodexKnowledge)
class CharacterCodexKnowledgeAdmin(admin.ModelAdmin):
    """Admin interface for CharacterCodexKnowledge (read-only debugging)."""

    list_display = [
        "roster_entry",
        "entry",
        "status",
        "learning_progress",
        "learned_from",
        "learned_at",
    ]
    list_filter = ["status", "entry__subject__category"]
    search_fields = ["roster_entry__character__db_key", "entry__name"]
    raw_id_fields = ["roster_entry", "learned_from"]
    readonly_fields = ["created_at"]

    fieldsets = (
        (None, {"fields": ("roster_entry", "entry")}),
        (
            "Status",
            {"fields": ("status", "learning_progress", "learned_from", "learned_at")},
        ),
        ("Timestamps", {"fields": ("created_at",), "classes": ["collapse"]}),
    )


@admin.register(CodexTeachingOffer)
class CodexTeachingOfferAdmin(admin.ModelAdmin):
    """Admin interface for CodexTeachingOffer."""

    autocomplete_fields = ["excluded_tenures", "visible_to_tenures"]

    list_display = ["teacher", "entry", "banked_ap", "gold_cost", "visibility_mode"]
    list_filter = ["visibility_mode", "entry__subject__category"]
    search_fields = ["teacher__roster_entry__character__db_key", "entry__name", "pitch"]
    raw_id_fields = ["teacher"]
    readonly_fields = ["created_at"]

    fieldsets = (
        (None, {"fields": ("teacher", "entry", "pitch")}),
        ("Costs", {"fields": ("banked_ap", "gold_cost")}),
        (
            "Visibility",
            {
                "fields": (
                    "visibility_mode",
                    "visible_to_tenures",
                    "visible_to_groups",
                    "excluded_tenures",
                ),
            },
        ),
        ("Timestamps", {"fields": ("created_at",), "classes": ["collapse"]}),
    )


@admin.register(OrganizationCodexGrant)
class OrganizationCodexGrantAdmin(admin.ModelAdmin):
    list_display = ("organization", "entry")
    search_fields = ("organization__name", "entry__name")
    autocomplete_fields = ("organization", "entry")
