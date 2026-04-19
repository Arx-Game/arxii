from django.contrib import admin
from django.db.models import Prefetch

from world.codex.models import TraditionCodexGrant
from world.magic.audere import AudereThreshold
from world.magic.models import (
    Affinity,
    AnimaRitualPerformance,
    Cantrip,
    CharacterAnima,
    CharacterAnimaRitual,
    CharacterAura,
    CharacterFacet,
    CharacterGift,
    CharacterResonance,
    CharacterTechnique,
    CharacterTradition,
    EffectType,
    Facet,
    Gift,
    IntensityTier,
    MishapPoolTier,
    Motif,
    MotifResonance,
    Reincarnation,
    Resonance,
    Restriction,
    SoulfrayConfig,
    Technique,
    TechniqueCapabilityGrant,
    TechniqueOutcomeModifier,
    TechniqueStyle,
    Tradition,
)


@admin.register(Affinity)
class AffinityAdmin(admin.ModelAdmin):
    list_display = ["name", "description"]
    search_fields = ["name"]


@admin.register(Resonance)
class ResonanceAdmin(admin.ModelAdmin):
    list_display = ["name", "affinity", "get_opposite"]
    list_filter = ["affinity"]
    search_fields = ["name"]
    list_select_related = ["affinity", "opposite"]

    @admin.display(description="Opposite")
    def get_opposite(self, obj: Resonance) -> str:
        return obj.opposite.name if obj.opposite else "-"


@admin.register(EffectType)
class EffectTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "base_power", "base_anima_cost", "has_power_scaling"]
    list_filter = ["has_power_scaling"]
    search_fields = ["name"]


@admin.register(TechniqueStyle)
class TechniqueStyleAdmin(admin.ModelAdmin):
    list_display = ["name", "get_paths"]
    search_fields = ["name", "description"]
    filter_horizontal = ["allowed_paths"]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .prefetch_related(Prefetch("allowed_paths", to_attr="cached_allowed_paths"))
        )

    @admin.display(description="Allowed Paths")
    def get_paths(self, obj):
        return ", ".join(p.name for p in obj.cached_allowed_paths[:5])


@admin.register(Restriction)
class RestrictionAdmin(admin.ModelAdmin):
    list_display = ["name", "power_bonus", "get_effect_types"]
    search_fields = ["name"]
    filter_horizontal = ["allowed_effect_types"]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .prefetch_related(
                Prefetch("allowed_effect_types", to_attr="cached_allowed_effect_types")
            )
        )

    @admin.display(description="Effect Types")
    def get_effect_types(self, obj):
        return ", ".join(et.name for et in obj.cached_allowed_effect_types[:5])


@admin.register(IntensityTier)
class IntensityTierAdmin(admin.ModelAdmin):
    list_display = ["name", "threshold", "control_modifier"]
    ordering = ["threshold"]
    search_fields = ["name", "description"]


class TechniqueCapabilityGrantInline(admin.TabularInline):
    model = TechniqueCapabilityGrant
    extra = 1
    autocomplete_fields = ["capability"]


@admin.register(Technique)
class TechniqueAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "gift",
        "style",
        "effect_type",
        "level",
        "get_tier",
        "intensity",
        "control",
        "anima_cost",
    ]
    list_filter = ["style", "effect_type", "gift", "source_cantrip"]
    filter_horizontal = ["restrictions"]
    search_fields = ["name", "description"]
    readonly_fields = ["get_tier"]
    autocomplete_fields = ["gift", "style", "effect_type", "source_cantrip"]
    list_select_related = ["gift", "style", "effect_type", "source_cantrip"]
    inlines = [TechniqueCapabilityGrantInline]

    @admin.display(description="Tier")
    def get_tier(self, obj: Technique) -> int:
        return obj.tier


@admin.register(CharacterAura)
class CharacterAuraAdmin(admin.ModelAdmin):
    list_display = ["character", "celestial", "primal", "abyssal", "get_dominant"]
    list_filter = ["updated_at"]
    search_fields = ["character__db_key"]
    readonly_fields = ["updated_at"]

    @admin.display(description="Dominant")
    def get_dominant(self, obj):
        return obj.dominant_affinity.label


@admin.register(CharacterResonance)
class CharacterResonanceAdmin(admin.ModelAdmin):
    list_display = ["character", "resonance", "scope", "strength", "is_active"]
    list_filter = ["scope", "strength", "is_active"]
    search_fields = ["character__db_key", "resonance__name"]
    autocomplete_fields = ["resonance"]
    list_select_related = ["character", "resonance", "resonance__affinity"]


@admin.register(Gift)
class GiftAdmin(admin.ModelAdmin):
    list_display = ["name"]
    search_fields = ["name", "description"]
    filter_horizontal = ["resonances"]


@admin.register(CharacterGift)
class CharacterGiftAdmin(admin.ModelAdmin):
    list_display = ["character", "gift", "acquired_at"]
    list_filter = ["gift"]
    search_fields = ["character__character__db_key", "gift__name"]
    date_hierarchy = "acquired_at"


class TraditionCodexGrantInline(admin.TabularInline):
    model = TraditionCodexGrant
    extra = 1
    autocomplete_fields = ["entry"]


@admin.register(Tradition)
class TraditionAdmin(admin.ModelAdmin):
    list_display = ["name", "society", "is_active", "sort_order"]
    list_filter = ["is_active"]
    search_fields = ["name", "description"]
    raw_id_fields = ["society"]
    list_editable = ["sort_order", "is_active"]
    inlines = [TraditionCodexGrantInline]


@admin.register(CharacterTradition)
class CharacterTraditionAdmin(admin.ModelAdmin):
    list_display = ["character", "tradition", "acquired_at"]
    list_filter = ["tradition"]
    search_fields = ["character__character__db_key", "tradition__name"]
    raw_id_fields = ["character"]
    date_hierarchy = "acquired_at"


@admin.register(CharacterTechnique)
class CharacterTechniqueAdmin(admin.ModelAdmin):
    list_display = ["character", "technique", "acquired_at"]
    list_filter = ["technique__gift", "technique__style"]
    search_fields = ["character__character__db_key", "technique__name"]
    date_hierarchy = "acquired_at"


@admin.register(CharacterAnima)
class CharacterAnimaAdmin(admin.ModelAdmin):
    list_display = ["character", "current", "maximum", "last_recovery"]
    list_filter = ["last_recovery"]
    search_fields = ["character__db_key"]
    readonly_fields = ["last_recovery"]


class AnimaRitualPerformanceInline(admin.TabularInline):
    model = AnimaRitualPerformance
    extra = 0
    readonly_fields = ["performed_at"]


@admin.register(CharacterAnimaRitual)
class CharacterAnimaRitualAdmin(admin.ModelAdmin):
    list_display = ["character", "stat", "skill", "specialization", "resonance"]
    list_filter = ["stat", "skill", "resonance"]
    search_fields = ["character__character__db_key", "description"]
    inlines = [AnimaRitualPerformanceInline]


@admin.register(AnimaRitualPerformance)
class AnimaRitualPerformanceAdmin(admin.ModelAdmin):
    list_display = [
        "ritual",
        "target_character",
        "was_successful",
        "anima_recovered",
        "performed_at",
    ]
    list_filter = ["was_successful", "performed_at"]
    date_hierarchy = "performed_at"


class MotifResonanceInline(admin.TabularInline):
    model = MotifResonance
    extra = 0


@admin.register(Motif)
class MotifAdmin(admin.ModelAdmin):
    list_display = ["__str__", "character"]
    search_fields = ["character__character__db_key", "description"]
    inlines = [MotifResonanceInline]


@admin.register(Facet)
class FacetAdmin(admin.ModelAdmin):
    """Admin for hierarchical Facet model."""

    list_display = ["name", "parent", "get_depth", "get_full_path"]
    list_filter = ["parent"]
    search_fields = ["name", "description"]
    autocomplete_fields = ["parent"]
    ordering = ["parent__name", "name"]

    @admin.display(description="Depth")
    def get_depth(self, obj):
        return obj.depth

    @admin.display(description="Full Path")
    def get_full_path(self, obj):
        return obj.full_path


@admin.register(CharacterFacet)
class CharacterFacetAdmin(admin.ModelAdmin):
    """Admin for CharacterFacet assignments."""

    list_display = ["character", "facet", "resonance", "get_facet_path"]
    list_filter = ["resonance", "facet__parent"]
    search_fields = [
        "character__character__db_key",
        "facet__name",
        "resonance__name",
        "flavor_text",
    ]
    autocomplete_fields = ["facet", "resonance"]
    list_select_related = ["character", "facet", "facet__parent", "resonance"]

    @admin.display(description="Facet Path")
    def get_facet_path(self, obj):
        return obj.facet.full_path


@admin.register(Reincarnation)
class ReincarnationAdmin(admin.ModelAdmin):
    list_display = ["character", "gift", "past_life_name"]
    list_filter = ["character"]
    search_fields = ["past_life_name", "character__character__db_key"]
    raw_id_fields = ["character", "gift"]


@admin.register(Cantrip)
class CantripAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "archetype",
        "effect_type",
        "style",
        "base_intensity",
        "base_control",
        "base_anima_cost",
        "requires_facet",
        "is_active",
        "sort_order",
    ]
    list_filter = ["archetype", "effect_type", "style", "requires_facet", "is_active"]
    filter_horizontal = ["allowed_facets"]
    search_fields = ["name", "description"]
    autocomplete_fields = ["effect_type", "style"]
    list_select_related = ["effect_type", "style"]


@admin.register(AudereThreshold)
class AudereThresholdAdmin(admin.ModelAdmin):
    list_display = (
        "minimum_intensity_tier",
        "minimum_warp_stage",
        "intensity_bonus",
        "anima_pool_bonus",
        "warp_multiplier",
    )


@admin.register(SoulfrayConfig)
class SoulfrayConfigAdmin(admin.ModelAdmin):
    list_display = [
        "soulfray_threshold_ratio",
        "severity_scale",
        "deficit_scale",
        "resilience_check_type",
        "base_check_difficulty",
    ]


@admin.register(MishapPoolTier)
class MishapPoolTierAdmin(admin.ModelAdmin):
    list_display = ["min_deficit", "max_deficit", "consequence_pool"]


@admin.register(TechniqueOutcomeModifier)
class TechniqueOutcomeModifierAdmin(admin.ModelAdmin):
    list_display = ["outcome", "modifier_value"]
