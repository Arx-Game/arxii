from django.contrib import admin, messages

from world.admin_utils import OneRowPerFormSet
from world.classes.models import (
    Aspect,
    CharacterClass,
    ClassStageHealthRate,
    DistinctionPathAspectGrant,
    Path,
    PathAspect,
)
from world.codex.admin import GrantReachOnSaveMixin
from world.codex.models import PathCodexGrant
from world.contributors.admin import CREDIT_FIELDSET
from world.magic.models import PathGiftGrant
from world.magic.services.magic_skills import invalidate_technique_own_paths
from world.mechanics.services import ensure_aspect_target
from world.progression.models import CodexKnowledgeRequirement, TraitRequirement
from world.skills.models import PathSkillSuggestion


class PathAspectInline(admin.TabularInline):
    """Inline admin for aspects on a path."""

    model = PathAspect
    formset = OneRowPerFormSet
    extra = 1
    autocomplete_fields = ["aspect"]


class PathCodexGrantInline(admin.TabularInline):
    model = PathCodexGrant
    formset = OneRowPerFormSet
    extra = 1
    autocomplete_fields = ["entry"]


class PathSkillSuggestionInline(admin.TabularInline):
    model = PathSkillSuggestion
    formset = OneRowPerFormSet
    extra = 1
    fk_name = "character_path"
    autocomplete_fields = ["skill"]


class PathTraitRequirementInline(admin.TabularInline):
    """Inline for TraitRequirements attached to a Path (#2538).

    Lets staff author stat/skill prerequisites directly on a hybrid Path row.
    """

    model = TraitRequirement
    extra = 0
    fields = ["trait", "minimum_value", "is_active", "description"]
    autocomplete_fields = ["trait"]


class PathCodexKnowledgeRequirementInline(admin.TabularInline):
    """Inline for CodexKnowledgeRequirements attached to a Path (#2603).

    Lets staff author codex-knowledge prerequisites directly on a Path row.
    """

    model = CodexKnowledgeRequirement
    extra = 0
    fields = ["codex_entry", "is_active", "description"]
    autocomplete_fields = ["codex_entry"]


class PathGiftGrantInline(admin.TabularInline):
    """The path's curated starter technique pool per gift (#3712).

    The path half of the CG technique menu. Its tradition-side sibling has been
    inline-editable on ``TraditionAdmin`` since #2426; this half had no
    authoring surface at all, so the authored path pools could not be edited.
    ``filter_horizontal`` does not apply to an inline, so the standalone
    ``PathGiftGrantAdmin`` is where a pool is actually composed; this inline is
    the way in from the path, and shows which gifts the path grants.
    """

    model = PathGiftGrant
    formset = OneRowPerFormSet
    extra = 0
    fields = ["gift"]
    autocomplete_fields = ["gift"]
    show_change_link = True


@admin.register(Path)
class PathAdmin(GrantReachOnSaveMixin, admin.ModelAdmin):
    """Admin for character paths.

    A save can change a technique's own Paths (a grant removed inline, the Path's
    order), so it clears ``Technique.cached_own_paths`` (#4555).
    """

    list_display = [
        "name",
        "stage",
        "style",
        "minimum_level",
        "is_active",
        "parent_count",
        "aspect_summary",
    ]
    list_filter = ["stage", "is_active", "style"]
    search_fields = ["name", "description"]
    filter_horizontal = ["parent_paths"]
    autocomplete_fields = ["style", "technique_skill"]
    list_select_related = ["style"]
    inlines = [
        PathAspectInline,
        PathCodexGrantInline,
        PathSkillSuggestionInline,
        PathTraitRequirementInline,
        PathCodexKnowledgeRequirementInline,
        PathGiftGrantInline,
    ]
    fieldsets = (
        (None, {"fields": ("name", "description", "stage", "minimum_level")}),
        ("Casting", {"fields": ("technique_skill", "style", "action_category")}),
        ("Display", {"fields": ("icon_url", "icon_name", "sort_order", "is_active")}),
        ("Evolution", {"fields": ("parent_paths",)}),
        CREDIT_FIELDSET,
    )

    def save_related(self, request, form, formsets, change) -> None:
        super().save_related(request, form, formsets, change)
        invalidate_technique_own_paths()

    def delete_model(self, request, obj) -> None:
        super().delete_model(request, obj)
        invalidate_technique_own_paths()

    def delete_queryset(self, request, queryset) -> None:
        super().delete_queryset(request, queryset)
        invalidate_technique_own_paths()

    @admin.display(description="Parents")
    def parent_count(self, obj):
        return obj.parent_paths.count()

    @admin.display(description="Aspects")
    def aspect_summary(self, obj):
        return ", ".join(
            f"{pa.aspect.name}({pa.weight})" for pa in obj.path_aspects.select_related("aspect")
        )


@admin.register(Aspect)
class AspectAdmin(admin.ModelAdmin):
    """Admin for aspects."""

    list_display = ["name", "description", "path_count"]
    search_fields = ["name", "description"]

    @admin.display(description="Paths")
    def path_count(self, obj):
        return obj.path_aspects.count()

    def save_model(self, request, obj, form, change):
        """Save the Aspect and make sure a modifier target points at it (#4827).

        A distinction's ``+10 <aspect>`` can only name a ``ModifierTarget``, so every
        Aspect row needs one with ``target_aspect`` set. An explicit call, not a signal
        (ADR-0009).
        """
        super().save_model(request, obj, form, change)
        if ensure_aspect_target(obj) is None:
            messages.warning(
                request,
                f"No modifier target was made for {obj.name}: another category already "
                "has a target of that name. Point that row's target aspect at this Aspect "
                "on the Modifier targets admin, or rename one of them.",
            )


# ---------------------------------------------------------------------------
# #3831
# ---------------------------------------------------------------------------


class ClassStageHealthRateInline(admin.TabularInline):
    """#3831 - the per-stage health-per-level rates authored for a class."""

    model = ClassStageHealthRate
    formset = OneRowPerFormSet
    extra = 1


@admin.register(CharacterClass)
class CharacterClassAdmin(admin.ModelAdmin):
    """#3831 - the character class catalog (trait requirements, progression rules)."""

    list_display = ["name", "minimum_level", "is_hidden"]
    list_filter = ["is_hidden", "minimum_level"]
    search_fields = ["name", "description"]
    filter_horizontal = ["core_traits"]
    inlines = [ClassStageHealthRateInline]


@admin.register(ClassStageHealthRate)
class ClassStageHealthRateAdmin(admin.ModelAdmin):
    """#3831 - authored per-class health gained per level within a PathStage band."""

    list_display = ["character_class", "stage", "health_per_level"]
    list_filter = ["stage"]
    search_fields = ["character_class__name"]
    list_select_related = ["character_class"]
    autocomplete_fields = ["character_class"]


@admin.register(DistinctionPathAspectGrant)
class DistinctionPathAspectGrantAdmin(admin.ModelAdmin):
    """A card's bonus on the holder's Path's stronger Aspect (#4852, slice 6 of #4813)."""

    list_display = ("distinction", "value")
    search_fields = ("distinction__name",)
    raw_id_fields = ("distinction",)
