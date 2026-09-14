"""Admin registrations for buildings lookup tables (#670, #1469).

Only the tuning lookups are registered — Buildings themselves are
game-state mutated through services, not hand-edited.
"""

from typing import ClassVar

from django.contrib import admin

from world.buildings.models import (
    ArchitecturalStyle,
    BuildingKind,
    BuildingListing,
    BuildingSizeTier,
    DecorationAffinity,
    DecorationKind,
    MaterialLoreEffect,
    PolishCategory,
    ProjectTemplate,
    ProjectTemplatePolishIncrement,
    PropertyGrantProfile,
    StyleAffinity,
    TierThreshold,
)


@admin.register(BuildingSizeTier)
class BuildingSizeTierAdmin(admin.ModelAdmin):
    list_display: ClassVar[list[str]] = ["tier", "name", "space_budget"]
    ordering: ClassVar[list[str]] = ["tier"]


class StyleAffinityInline(admin.TabularInline):
    model = StyleAffinity
    extra = 0


@admin.register(ArchitecturalStyle)
class ArchitecturalStyleAdmin(admin.ModelAdmin):
    """The style catalog (#1469) — names, tiers, and placeholder magnitudes are content."""

    list_display: ClassVar[list[str]] = [
        "name",
        "is_default",
        "is_active",
        "prestige_bonus",
        "cost_multiplier",
        "codex_subject",
    ]
    list_filter: ClassVar[list[str]] = ["is_default", "is_active"]
    search_fields: ClassVar[list[str]] = ["name"]
    inlines: ClassVar[list[type[admin.TabularInline]]] = [StyleAffinityInline]


@admin.register(MaterialLoreEffect)
class MaterialLoreEffectAdmin(admin.ModelAdmin):
    """The material-lore catalog — content authored here, not in code (#695)."""

    list_display: ClassVar[list[str]] = [
        "template",
        "target_stat",
        "units_per_tier",
        "magnitude_per_tier",
        "max_tiers",
    ]
    list_filter: ClassVar[list[str]] = ["target_stat"]
    search_fields: ClassVar[list[str]] = ["template__name", "target_stat"]
    autocomplete_fields: ClassVar[list[str]] = ["template"]


# ---------------------------------------------------------------------------
# #3831
# ---------------------------------------------------------------------------


@admin.register(BuildingKind)
class BuildingKindAdmin(admin.ModelAdmin):
    """#3831 - the authorable building-category catalog (flags are sort/filter axes)."""

    list_display: ClassVar[list[str]] = [
        "name",
        "is_residential",
        "is_commercial",
        "is_fortified",
        "is_occult",
        "is_secret",
    ]
    list_filter: ClassVar[list[str]] = [
        "is_residential",
        "is_commercial",
        "is_fortified",
        "is_occult",
        "is_maritime",
        "is_agrarian",
        "is_aerial",
        "is_subterranean",
        "is_secret",
    ]
    search_fields: ClassVar[list[str]] = ["name", "description"]


@admin.register(PropertyGrantProfile)
class PropertyGrantProfileAdmin(admin.ModelAdmin):
    """#3831 - a reusable "grant a persona an existing Building" catalog row."""

    list_display: ClassVar[list[str]] = [
        "name",
        "building_kind",
        "initial_condition_tier",
        "activation_target_tier",
    ]
    list_filter: ClassVar[list[str]] = ["initial_condition_tier", "activation_target_tier"]
    search_fields: ClassVar[list[str]] = ["name"]
    list_select_related: ClassVar[list[str]] = ["building_kind", "ward_area"]
    autocomplete_fields: ClassVar[list[str]] = ["building_kind", "ward_area"]


@admin.register(BuildingListing)
class BuildingListingAdmin(admin.ModelAdmin):
    """#3831 - a staff/content-curated coin purchase front door onto a Building."""

    list_display: ClassVar[list[str]] = [
        "building",
        "price_coppers",
        "organization",
        "is_available",
        "sold_at",
    ]
    list_filter: ClassVar[list[str]] = ["is_available"]
    list_select_related: ClassVar[list[str]] = ["organization"]
    raw_id_fields: ClassVar[list[str]] = ["building", "sold_to_persona"]
    autocomplete_fields: ClassVar[list[str]] = ["organization"]


@admin.register(PolishCategory)
class PolishCategoryAdmin(admin.ModelAdmin):
    """#3831 - an admin-authored polish dimension (Opulence, Elegance, Provenance...)."""

    list_display: ClassVar[list[str]] = ["name"]
    search_fields: ClassVar[list[str]] = ["name", "description"]


@admin.register(TierThreshold)
class TierThresholdAdmin(admin.ModelAdmin):
    """#3831 - an admin-tunable label boundary for a polish category."""

    list_display: ClassVar[list[str]] = ["category", "tier_name", "min_value"]
    list_filter: ClassVar[list[str]] = ["category"]
    search_fields: ClassVar[list[str]] = ["tier_name", "category__name"]
    list_select_related: ClassVar[list[str]] = ["category"]
    autocomplete_fields: ClassVar[list[str]] = ["category"]


class ProjectTemplatePolishIncrementInline(admin.TabularInline):
    """#3831 - per-category polish increments a project template grants."""

    model = ProjectTemplatePolishIncrement
    extra = 1
    autocomplete_fields = ["category"]


@admin.register(ProjectTemplate)
class ProjectTemplateAdmin(admin.ModelAdmin):
    """#3831 - an admin-authored template for a polish-adding project."""

    list_display: ClassVar[list[str]] = [
        "name",
        "base_cost",
        "weekly_upkeep_cost",
        "project_kind",
    ]
    list_filter: ClassVar[list[str]] = ["project_kind"]
    search_fields: ClassVar[list[str]] = ["name", "description"]
    filter_horizontal: ClassVar[list[str]] = ["tier_prerequisites"]
    inlines = [ProjectTemplatePolishIncrementInline]


@admin.register(ProjectTemplatePolishIncrement)
class ProjectTemplatePolishIncrementAdmin(admin.ModelAdmin):
    """#3831 - one (template, category) polish increment row."""

    list_display: ClassVar[list[str]] = ["template", "category", "value"]
    list_filter: ClassVar[list[str]] = ["category"]
    search_fields: ClassVar[list[str]] = ["template__name", "category__name"]
    list_select_related: ClassVar[list[str]] = ["template", "category"]
    autocomplete_fields: ClassVar[list[str]] = ["template", "category"]


@admin.register(DecorationKind)
class DecorationKindAdmin(admin.ModelAdmin):
    """#3831 - a catalog decoration/furnishing that passively mods room comfort."""

    list_display: ClassVar[list[str]] = [
        "name",
        "amenity",
        "cost_coppers",
        "crafted_item_template",
    ]
    search_fields: ClassVar[list[str]] = ["name", "description"]
    list_select_related: ClassVar[list[str]] = ["crafted_item_template"]
    autocomplete_fields: ClassVar[list[str]] = ["crafted_item_template"]


@admin.register(DecorationAffinity)
class DecorationAffinityAdmin(admin.ModelAdmin):
    """#3831 - one discomfort-mitigation a decoration kind imparts."""

    list_display: ClassVar[list[str]] = ["kind", "stat_key", "value"]
    list_filter: ClassVar[list[str]] = ["stat_key"]
    search_fields: ClassVar[list[str]] = ["kind__name"]
    list_select_related: ClassVar[list[str]] = ["kind"]
    autocomplete_fields: ClassVar[list[str]] = ["kind"]
