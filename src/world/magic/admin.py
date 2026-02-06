from django.contrib import admin

from world.magic.models import (
    AnimaRitualPerformance,
    CharacterAnima,
    CharacterAnimaRitual,
    CharacterAura,
    CharacterFacet,
    CharacterGift,
    CharacterResonance,
    CharacterTechnique,
    EffectType,
    Facet,
    Gift,
    IntensityTier,
    Motif,
    MotifResonance,
    Restriction,
    Technique,
    TechniqueStyle,
    Thread,
    ThreadJournal,
    ThreadResonance,
    ThreadType,
)

# Note: Affinity and Resonance are now managed via ModifierType in the mechanics app.
# See world.mechanics.admin for their admin interfaces.


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
        return super().get_queryset(request).prefetch_related("allowed_paths")

    @admin.display(description="Allowed Paths")
    def get_paths(self, obj):
        return ", ".join(p.name for p in obj.allowed_paths.all()[:5])


@admin.register(Restriction)
class RestrictionAdmin(admin.ModelAdmin):
    list_display = ["name", "power_bonus", "get_effect_types"]
    search_fields = ["name"]
    filter_horizontal = ["allowed_effect_types"]

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("allowed_effect_types")

    @admin.display(description="Effect Types")
    def get_effect_types(self, obj):
        return ", ".join(et.name for et in obj.allowed_effect_types.all()[:5])


@admin.register(IntensityTier)
class IntensityTierAdmin(admin.ModelAdmin):
    list_display = ["name", "threshold", "control_modifier"]
    ordering = ["threshold"]
    search_fields = ["name", "description"]


@admin.register(Technique)
class TechniqueAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "gift",
        "style",
        "effect_type",
        "level",
        "get_tier",
        "get_calculated_power",
        "anima_cost",
    ]
    list_filter = ["style", "effect_type", "gift"]
    filter_horizontal = ["restrictions"]
    search_fields = ["name", "description"]
    readonly_fields = ["get_tier", "get_calculated_power"]
    autocomplete_fields = ["gift", "style", "effect_type"]
    list_select_related = ["gift", "style", "effect_type"]

    @admin.display(description="Tier")
    def get_tier(self, obj):
        return obj.tier

    @admin.display(description="Power")
    def get_calculated_power(self, obj):
        power = obj.calculated_power
        return power if power is not None else "N/A"


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
    list_select_related = ["character", "resonance", "resonance__category"]


@admin.register(Gift)
class GiftAdmin(admin.ModelAdmin):
    list_display = ["name", "affinity"]
    search_fields = ["name", "description"]
    filter_horizontal = ["resonances"]
    autocomplete_fields = ["affinity"]
    list_select_related = ["affinity", "affinity__category"]


@admin.register(CharacterGift)
class CharacterGiftAdmin(admin.ModelAdmin):
    list_display = ["character", "gift", "acquired_at"]
    list_filter = ["gift"]
    search_fields = ["character__character__db_key", "gift__name"]
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


@admin.register(ThreadType)
class ThreadTypeAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "slug",
        "romantic_threshold",
        "trust_threshold",
        "rivalry_threshold",
        "protective_threshold",
        "enmity_threshold",
    ]
    search_fields = ["name", "slug", "description"]
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ["grants_resonance"]


class ThreadResonanceInline(admin.TabularInline):
    model = ThreadResonance
    extra = 0
    autocomplete_fields = ["resonance"]


class ThreadJournalInline(admin.TabularInline):
    model = ThreadJournal
    extra = 0
    readonly_fields = ["created_at"]
    fields = ["author", "content", "created_at"]


@admin.register(Thread)
class ThreadAdmin(admin.ModelAdmin):
    list_display = [
        "initiator",
        "receiver",
        "romantic",
        "trust",
        "rivalry",
        "protective",
        "enmity",
        "is_soul_tether",
    ]
    list_filter = ["is_soul_tether", "created_at"]
    search_fields = ["initiator__db_key", "receiver__db_key"]
    inlines = [ThreadResonanceInline, ThreadJournalInline]


@admin.register(ThreadJournal)
class ThreadJournalAdmin(admin.ModelAdmin):
    list_display = ["thread", "author", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["thread__initiator__db_key", "thread__receiver__db_key"]
    readonly_fields = ["created_at"]


@admin.register(ThreadResonance)
class ThreadResonanceAdmin(admin.ModelAdmin):
    list_display = ["thread", "resonance", "strength"]
    list_filter = ["strength"]
    search_fields = ["thread__initiator__db_key", "thread__receiver__db_key"]
    autocomplete_fields = ["resonance"]
    list_select_related = ["thread", "resonance", "resonance__category"]


class MotifResonanceInline(admin.TabularInline):
    model = MotifResonance
    extra = 0


@admin.register(Motif)
class MotifAdmin(admin.ModelAdmin):
    list_display = ["__str__", "character"]
    search_fields = ["character__character__db_key", "description"]
    inlines = [MotifResonanceInline]


@admin.register(MotifResonance)
class MotifResonanceAdmin(admin.ModelAdmin):
    list_display = ["motif", "resonance", "is_from_gift", "get_facets"]
    list_filter = ["is_from_gift", "resonance"]

    @admin.display(description="Facets")
    def get_facets(self, obj):
        return ", ".join(a.facet.name for a in obj.facet_assignments.all())


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
