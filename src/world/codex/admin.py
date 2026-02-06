"""Django admin configuration for the codex system."""

from django.contrib import admin

from world.codex.models import (
    BeginningsCodexGrant,
    CharacterClueKnowledge,
    CharacterCodexKnowledge,
    CodexCategory,
    CodexClue,
    CodexEntry,
    CodexSubject,
    CodexTeachingOffer,
    DistinctionCodexGrant,
    PathCodexGrant,
)


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


@admin.register(CodexEntry)
class CodexEntryAdmin(admin.ModelAdmin):
    """Admin interface for CodexEntry."""

    list_display = [
        "name",
        "subject",
        "modifier_type",
        "share_cost",
        "learn_cost",
        "learn_threshold",
        "prerequisite_count",
    ]
    list_filter = ["subject__category", "subject", "modifier_type__category"]
    search_fields = ["name", "subject__name", "lore_content", "mechanics_content"]
    filter_horizontal = ["prerequisites"]
    ordering = ["subject", "display_order", "name"]

    fieldsets = (
        (None, {"fields": ("subject", "name", "summary")}),
        (
            "Content",
            {
                "fields": ("lore_content", "mechanics_content"),
                "description": "At least one content field (lore or mechanics) is required.",
            },
        ),
        (
            "Costs",
            {
                "fields": ("share_cost", "learn_cost"),
                "description": "AP costs for teaching and learning.",
            },
        ),
        (
            "Learning",
            {
                "fields": ("learn_difficulty", "learn_threshold"),
                "description": "Difficulty and progress required to learn.",
            },
        ),
        ("Prerequisites", {"fields": ("prerequisites",)}),
        (
            "Mechanics Link",
            {
                "fields": ("modifier_type",),
                "description": "Link to a modifier type (resonance, stat, etc.) "
                "this entry documents.",
            },
        ),
        ("Display", {"fields": ("display_order", "is_public"), "classes": ["collapse"]}),
    )
    autocomplete_fields = ["modifier_type"]

    def prerequisite_count(self, obj: CodexEntry) -> int:
        return obj.prerequisites.count()

    prerequisite_count.short_description = "Prerequisites"


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


@admin.register(CodexClue)
class CodexClueAdmin(admin.ModelAdmin):
    """Admin interface for CodexClue."""

    list_display = ["name", "entry", "research_value"]
    list_filter = ["entry__subject__category"]
    search_fields = ["name", "description", "entry__name"]
    autocomplete_fields = ["entry"]


@admin.register(CharacterClueKnowledge)
class CharacterClueKnowledgeAdmin(admin.ModelAdmin):
    """Admin interface for CharacterClueKnowledge (read-only debugging)."""

    list_display = ["roster_entry", "clue", "found_at"]
    list_filter = ["found_at"]
    search_fields = ["roster_entry__character__db_key", "clue__name"]
    readonly_fields = ["found_at"]


@admin.register(CodexTeachingOffer)
class CodexTeachingOfferAdmin(admin.ModelAdmin):
    """Admin interface for CodexTeachingOffer."""

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


# CG Grant Admins - These would typically be inlined in their source model admins


@admin.register(BeginningsCodexGrant)
class BeginningsCodexGrantAdmin(admin.ModelAdmin):
    """Admin interface for BeginningsCodexGrant."""

    list_display = ["beginnings", "entry"]
    list_filter = ["beginnings__starting_area__realm"]
    search_fields = ["beginnings__name", "entry__name"]
    raw_id_fields = ["beginnings", "entry"]


@admin.register(PathCodexGrant)
class PathCodexGrantAdmin(admin.ModelAdmin):
    """Admin interface for PathCodexGrant."""

    list_display = ["path", "entry"]
    search_fields = ["path__name", "entry__name"]
    raw_id_fields = ["path", "entry"]


@admin.register(DistinctionCodexGrant)
class DistinctionCodexGrantAdmin(admin.ModelAdmin):
    """Admin interface for DistinctionCodexGrant."""

    list_display = ["distinction", "entry"]
    list_filter = ["distinction__category"]
    search_fields = ["distinction__name", "entry__name"]
    raw_id_fields = ["distinction", "entry"]
