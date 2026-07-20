from django.contrib import admin
from django.db.models import Prefetch

from world.codex.models import TraditionCodexGrant
from world.magic.audere import AudereThreshold
from world.magic.models import (
    Affinity,
    AffinityInteraction,
    AnimaRitualBudgetAward,
    AnimaRitualPerformance,
    CharacterAnima,
    CharacterAura,
    CharacterGift,
    CharacterGiftUnlock,
    CharacterResonance,
    CharacterTechnique,
    CharacterThreadWeavingUnlock,
    CharacterTradition,
    CompromiseActType,
    CovenantRoleBlendConfig,
    CrossingChoice,
    CrossingOption,
    DistinctionResonanceRankThreshold,
    EffectType,
    Facet,
    Gift,
    GiftAcquisitionConfig,
    GiftUnlock,
    GlimpseTag,
    GlimpseTagDistinctionSuggestion,
    ImbuingProseTemplate,
    IntensityTier,
    LevelPowerConfig,
    MagicProgressionMilestone,
    MishapPoolTier,
    Motif,
    MotifResonance,
    MotifResonanceStyle,
    PoseEndorsement,
    Reincarnation,
    RelationshipBondPullTuning,
    Resonance,
    ResonanceEnvironmentConfig,
    ResonanceGainConfig,
    ResonanceGrant,
    Restriction,
    Ritual,
    RitualCheckConfig,
    RitualComponentRequirement,
    SanctumDissolutionRecoveryAward,
    SanctumHomecomingGainAward,
    SanctumPurgingRetentionAward,
    SceneEntryEndorsement,
    SignatureMotifBonus,
    SignatureMotifBonusAppliedCondition,
    SignatureMotifBonusCapabilityGrant,
    SignatureMotifBonusDamageProfile,
    SoulfrayConfig,
    SoulTetherConfig,
    StandingCapBand,
    Technique,
    TechniqueCapabilityGrant,
    TechniqueFunctionTag,
    TechniqueGrant,
    TechniqueOutcomeModifier,
    TechniqueRemovedCondition,
    TechniqueStyle,
    TechniqueTeachingOffer,
    Thread,
    ThreadLevelUnlock,
    ThreadPullCost,
    ThreadPullEffect,
    ThreadSurvivabilityTuning,
    ThreadWeavingTeachingOffer,
    ThreadWeavingUnlock,
    ThreadXPLockedLevel,
    TouchstoneCastConfig,
    Tradition,
    TraditionGiftGrant,
)
from world.magic.models.dramatic_moment import (
    DramaticMomentSuggestion,
    DramaticMomentTag,
    DramaticMomentType,
)
from world.magic.services.glimpse import refresh_glimpse_state


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


@admin.register(AffinityInteraction)
class AffinityInteractionAdmin(admin.ModelAdmin):
    list_display = [
        "source_affinity",
        "environment_affinity",
        "valence",
        "kind",
        "aggressor",
        "severity_multiplier",
    ]
    list_filter = ["valence", "kind"]
    raw_id_fields = ["source_affinity", "environment_affinity"]


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


@admin.register(TechniqueRemovedCondition)
class TechniqueRemovedConditionAdmin(admin.ModelAdmin):
    """Dispel/cleanse payload rows (#1585) — also editable inline on Technique."""

    list_display = [
        "technique",
        "condition",
        "target_kind",
        "minimum_success_level",
        "remove_all_stacks",
    ]
    list_filter = ["target_kind", "remove_all_stacks"]
    search_fields = ["technique__name", "condition__name"]
    autocomplete_fields = ["technique", "condition"]


class TechniqueRemovedConditionInline(admin.TabularInline):
    """Inline dispel payload rows on the Technique admin (#1585)."""

    model = TechniqueRemovedCondition
    extra = 1
    autocomplete_fields = ["condition"]


class TechniqueFunctionTagInline(admin.TabularInline):
    """Inline fine-grained function labels on the Technique admin (#2443)."""

    model = TechniqueFunctionTag
    extra = 1


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
        "archetype_alignment",
    ]
    list_filter = ["style", "effect_type", "gift", "archetype_alignment"]
    filter_horizontal = ["restrictions", "target_prerequisites"]
    search_fields = ["name", "description"]
    readonly_fields = ["get_tier"]
    autocomplete_fields = ["creator", "effect_type", "gift", "style"]
    list_select_related = ["gift", "style", "effect_type"]
    inlines = [
        TechniqueCapabilityGrantInline,
        TechniqueRemovedConditionInline,
        TechniqueFunctionTagInline,
    ]

    @admin.display(description="Tier")
    def get_tier(self, obj: Technique) -> int:
        return obj.tier


@admin.register(CharacterAura)
class CharacterAuraAdmin(admin.ModelAdmin):
    autocomplete_fields = ["character"]
    list_display = ["character", "celestial", "primal", "abyssal", "get_dominant"]
    list_filter = ["updated_at"]
    search_fields = ["character__db_key"]
    readonly_fields = ["updated_at", "glimpse_state"]

    @admin.display(description="Dominant")
    def get_dominant(self, obj):
        return obj.dominant_affinity.label

    def save_model(self, request, obj, form, change):
        """Keep the glimpse_state cache truthful after an admin prose/tag edit (#2427).

        ``glimpse_state`` is service-maintained (see the model field's help_text);
        editing ``glimpse_story`` here would otherwise desync the cache from the
        prose it's supposed to reflect.
        """
        super().save_model(request, obj, form, change)
        refresh_glimpse_state(obj)


@admin.register(GlimpseTag)
class GlimpseTagAdmin(admin.ModelAdmin):
    """Guided glimpse tag catalog (#2427) — lore-repo content model."""

    list_display = ["name", "axis", "sort_order", "is_active"]
    list_filter = ["axis", "is_active"]
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}
    filter_horizontal = ["paths"]


@admin.register(GlimpseTagDistinctionSuggestion)
class GlimpseTagDistinctionSuggestionAdmin(admin.ModelAdmin):
    """Curated tag→distinction suggestion (#2427) — lore-repo content model."""

    list_display = ["tag", "distinction", "sort_order"]
    list_filter = ["tag__axis"]
    search_fields = ["tag__name", "distinction__name"]


@admin.action(description="Staff grant resonance to this row")
def grant_resonance_action(modeladmin, request, queryset):  # type: ignore[no-untyped-def]  # noqa: ARG001
    """Admin action: grant each selected row 1 resonance via STAFF_GRANT.

    Quick form-less grant. For nuanced grants (custom amount / reason) use
    a proper Django admin intermediate page — future enhancement.
    """
    from world.magic.constants import GainSource  # noqa: PLC0415
    from world.magic.services.resonance import grant_resonance  # noqa: PLC0415

    for cr in queryset:
        grant_resonance(
            cr.character_sheet,
            cr.resonance,
            1,
            source=GainSource.STAFF_GRANT,
            staff_account=request.user,
        )


@admin.register(CharacterResonance)
class CharacterResonanceAdmin(admin.ModelAdmin):
    list_display = [
        "character_sheet",
        "resonance",
        "balance",
        "lifetime_earned",
        "claimed_at",
    ]
    search_fields = ["character_sheet__character__db_key", "resonance__name"]
    autocomplete_fields = ["character_sheet", "resonance"]
    list_select_related = [
        "character_sheet",
        "character_sheet__character",
        "resonance",
        "resonance__affinity",
    ]
    actions = [grant_resonance_action]


@admin.register(Gift)
class GiftAdmin(admin.ModelAdmin):
    autocomplete_fields = ["creator"]
    list_display = ["name"]
    search_fields = ["name", "description"]
    filter_horizontal = ["resonances"]


@admin.register(CharacterGift)
class CharacterGiftAdmin(admin.ModelAdmin):
    autocomplete_fields = ["character"]
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
    list_display = ["name", "is_active", "sort_order"]
    list_filter = ["is_active"]
    search_fields = ["name", "description"]
    list_editable = ["sort_order", "is_active"]
    inlines = [TraditionCodexGrantInline]


@admin.register(TraditionGiftGrant)
class TraditionGiftGrantAdmin(admin.ModelAdmin):
    list_display = ["tradition", "gift"]
    list_filter = ["tradition", "gift"]
    search_fields = ["tradition__name", "gift__name"]
    filter_horizontal = ["signature_techniques"]


@admin.register(CharacterTradition)
class CharacterTraditionAdmin(admin.ModelAdmin):
    list_display = ["character", "tradition", "acquired_at", "left_at"]
    list_filter = ["tradition"]
    search_fields = ["character__character__db_key", "tradition__name"]
    raw_id_fields = ["character"]
    date_hierarchy = "acquired_at"


@admin.register(CharacterTechnique)
class CharacterTechniqueAdmin(admin.ModelAdmin):
    autocomplete_fields = ["character"]
    list_display = ["character", "technique", "acquired_at"]
    list_filter = ["technique__gift", "technique__style"]
    search_fields = ["character__character__db_key", "technique__name"]
    date_hierarchy = "acquired_at"


@admin.register(CharacterAnima)
class CharacterAnimaAdmin(admin.ModelAdmin):
    autocomplete_fields = ["character"]
    list_display = ["character", "current", "maximum", "last_recovery"]
    list_filter = ["last_recovery"]
    search_fields = ["character__db_key"]
    readonly_fields = ["last_recovery"]


class AnimaRitualPerformanceInline(admin.TabularInline):
    model = AnimaRitualPerformance
    extra = 0
    readonly_fields = ["performed_at"]


@admin.register(AnimaRitualPerformance)
class AnimaRitualPerformanceAdmin(admin.ModelAdmin):
    autocomplete_fields = ["scene", "target_character"]
    list_display = [
        "ritual",
        "target_character",
        "was_successful",
        "anima_recovered",
        "performed_at",
    ]
    list_filter = ["was_successful", "performed_at"]
    date_hierarchy = "performed_at"


class MotifResonanceStyleInline(admin.TabularInline):
    model = MotifResonanceStyle
    extra = 1
    autocomplete_fields = ["style"]


class MotifResonanceInline(admin.TabularInline):
    model = MotifResonance
    extra = 0


@admin.register(Motif)
class MotifAdmin(admin.ModelAdmin):
    autocomplete_fields = ["character"]
    list_display = ["__str__", "character"]
    search_fields = ["character__character__db_key", "description"]
    inlines = [MotifResonanceInline]


@admin.register(MotifResonance)
class MotifResonanceAdmin(admin.ModelAdmin):
    list_display = ["__str__", "motif", "resonance", "is_from_gift"]
    list_filter = ["is_from_gift", "resonance__affinity"]
    search_fields = ["motif__character__character__db_key", "resonance__name"]
    list_select_related = ["motif", "resonance", "resonance__affinity"]
    raw_id_fields = ["motif"]
    autocomplete_fields = ["resonance"]
    inlines = [MotifResonanceStyleInline]


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


@admin.register(Reincarnation)
class ReincarnationAdmin(admin.ModelAdmin):
    list_display = ["character", "gift", "past_life_name"]
    list_filter = ["character"]
    search_fields = ["past_life_name", "character__character__db_key"]
    raw_id_fields = ["character", "gift"]


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


@admin.register(AnimaRitualBudgetAward)
class AnimaRitualBudgetAwardAdmin(admin.ModelAdmin):
    """#1207 — anima/severity budget per outcome tier (staff-tunable)."""

    list_display = ("outcome_tier", "budget")
    list_select_related = ("outcome_tier",)
    ordering = ("outcome_tier__success_level",)


@admin.register(SanctumHomecomingGainAward)
class SanctumHomecomingGainAwardAdmin(admin.ModelAdmin):
    """#1207 — Homecoming ritual gain multiplier per outcome tier (staff-tunable)."""

    list_display = ("outcome_tier", "gain_multiplier")
    list_select_related = ("outcome_tier",)
    ordering = ("outcome_tier__success_level",)


@admin.register(SanctumPurgingRetentionAward)
class SanctumPurgingRetentionAwardAdmin(admin.ModelAdmin):
    """#1207 — Purging ritual retention adjustment per outcome tier (staff-tunable)."""

    list_display = ("outcome_tier", "retention_modifier")
    list_select_related = ("outcome_tier",)
    ordering = ("outcome_tier__success_level",)


@admin.register(SanctumDissolutionRecoveryAward)
class SanctumDissolutionRecoveryAwardAdmin(admin.ModelAdmin):
    """#1207 — Dissolution ritual recovery fraction per outcome tier (staff-tunable)."""

    list_display = ("outcome_tier", "recovery_fraction")
    list_select_related = ("outcome_tier",)
    ordering = ("outcome_tier__success_level",)


@admin.register(LevelPowerConfig)
class LevelPowerConfigAdmin(admin.ModelAdmin):
    """Singleton tuning config for level→power bonuses."""

    list_display = ("pk", "character_level_bonus", "technique_level_bonus")

    def has_add_permission(self, request) -> bool:  # noqa: ARG002
        return not LevelPowerConfig.objects.exists()

    def has_delete_permission(self, request, obj=None) -> bool:  # noqa: ARG002
        return False


@admin.register(CovenantRoleBlendConfig)
class CovenantRoleBlendConfigAdmin(admin.ModelAdmin):
    """Singleton tuning config for the covenant-role blend power term (#2529)."""

    list_display = ("pk", "multiplier_tenths")

    def has_add_permission(self, request) -> bool:  # noqa: ARG002
        return not CovenantRoleBlendConfig.objects.exists()

    def has_delete_permission(self, request, obj=None) -> bool:  # noqa: ARG002
        return False


@admin.register(StandingCapBand)
class StandingCapBandAdmin(admin.ModelAdmin):
    """Staff authoring surface for per-level resonance-standing cap bands (#853)."""

    list_display = ("min_level", "cap", "mode", "diminish_pct")
    ordering = ("min_level",)


@admin.register(ResonanceGainConfig)
class ResonanceGainConfigAdmin(admin.ModelAdmin):
    """Singleton tuning config — one row per environment."""

    autocomplete_fields = ["updated_by"]

    list_display = (
        "pk",
        "weekly_pot_per_character",
        "scene_entry_grant",
        "residence_daily_trickle_per_resonance",
        "outfit_daily_trickle_per_item_resonance",
        "same_pair_daily_cap",
        "settlement_day_of_week",
        "updated_at",
    )

    def has_add_permission(self, request) -> bool:  # noqa: ARG002
        return not ResonanceGainConfig.objects.exists()

    def has_delete_permission(self, request, obj=None) -> bool:  # noqa: ARG002
        return False


@admin.register(ResonanceEnvironmentConfig)
class ResonanceEnvironmentConfigAdmin(admin.ModelAdmin):
    """Singleton tuning config for the resonance-environment primitive."""

    autocomplete_fields = ["updated_by"]

    list_display = (
        "pk",
        "base_coefficient",
        "caster_power_scalar",
        "balanced_band",
        "backfire_base_difficulty",
        "backfire_difficulty_per_magnitude",
        "updated_at",
    )

    def has_add_permission(self, request) -> bool:  # noqa: ARG002
        return not ResonanceEnvironmentConfig.objects.exists()

    def has_delete_permission(self, request, obj=None) -> bool:  # noqa: ARG002
        return False


@admin.register(MishapPoolTier)
class MishapPoolTierAdmin(admin.ModelAdmin):
    list_display = ["min_deficit", "max_deficit", "consequence_pool"]


@admin.register(TechniqueOutcomeModifier)
class TechniqueOutcomeModifierAdmin(admin.ModelAdmin):
    list_display = ["outcome", "modifier_value"]


@admin.register(ThreadPullCost)
class ThreadPullCostAdmin(admin.ModelAdmin):
    list_display = [
        "tier",
        "target_kind",
        "label",
        "resonance_cost",
        "anima_per_thread",
        "imbue_cost_multiplier",
    ]
    list_filter = ["target_kind", "tier"]
    ordering = ["tier", "target_kind"]


@admin.register(ThreadXPLockedLevel)
class ThreadXPLockedLevelAdmin(admin.ModelAdmin):
    list_display = ["level", "xp_cost"]
    ordering = ["level"]


@admin.register(DistinctionResonanceRankThreshold)
class DistinctionResonanceRankThresholdAdmin(admin.ModelAdmin):
    """Reverse sidecar of the distinction currency-knob grant (#2037 Decision 8)."""

    list_display = ["distinction", "resonance", "rank", "lifetime_earned_threshold"]
    list_filter = ["resonance"]
    search_fields = ["distinction__name", "resonance__name"]
    autocomplete_fields = ["distinction", "resonance"]
    list_select_related = ["distinction", "resonance"]
    ordering = ["distinction_id", "resonance_id", "rank"]


@admin.register(ThreadPullEffect)
class ThreadPullEffectAdmin(admin.ModelAdmin):
    list_display = [
        "target_kind",
        "resonance",
        "tier",
        "min_thread_level",
        "effect_kind",
    ]
    list_filter = ["target_kind", "tier", "effect_kind"]
    search_fields = ["resonance__name", "narrative_snippet"]
    autocomplete_fields = ["resonance", "capability_grant"]
    list_select_related = ["resonance", "capability_grant"]


@admin.register(ThreadSurvivabilityTuning)
class ThreadSurvivabilityTuningAdmin(admin.ModelAdmin):
    """Per-target tuning for the universal thread survivability baseline (#1175)."""

    list_display = ("vital_target", "coefficient", "cap", "half_saturation")
    list_editable = ("coefficient", "cap", "half_saturation")


@admin.register(ImbuingProseTemplate)
class ImbuingProseTemplateAdmin(admin.ModelAdmin):
    list_display = ["resonance", "target_kind"]
    list_filter = ["target_kind"]
    search_fields = ["resonance__name", "prose"]
    autocomplete_fields = ["resonance"]
    list_select_related = ["resonance"]


class RitualComponentRequirementInline(admin.TabularInline):
    model = RitualComponentRequirement
    extra = 0
    autocomplete_fields = ["item_template"]
    raw_id_fields = ["min_quality_tier"]


class RitualCheckConfigInline(admin.StackedInline):
    model = RitualCheckConfig
    extra = 0
    can_delete = True
    autocomplete_fields = ["stat", "skill", "specialization", "resonance", "check_type"]


@admin.register(Ritual)
class RitualAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "execution_kind",
        "hedge_accessible",
        "glimpse_eligible",
    ]
    list_filter = ["execution_kind", "hedge_accessible", "glimpse_eligible"]
    search_fields = ["name", "description"]
    autocomplete_fields = ["author_account", "flow", "site_property"]
    inlines = [RitualComponentRequirementInline, RitualCheckConfigInline]
    # Dispatch fields (execution_kind / service_function_path / flow)
    # determine WHICH code runs when a ritual is performed. Exposing them
    # as editable is an arbitrary-import RCE vector if a staff cookie is
    # compromised — admin could rewrite the path to point at any sensitive
    # service function and trigger it via the ritual UI. Manage these
    # fields via seed code instead.
    readonly_fields = ["execution_kind", "service_function_path", "flow"]


@admin.register(RitualComponentRequirement)
class RitualComponentRequirementAdmin(admin.ModelAdmin):
    list_display = ["ritual", "item_template", "quantity", "min_quality_tier"]
    list_filter = ["ritual"]
    autocomplete_fields = ["ritual", "item_template"]
    raw_id_fields = ["min_quality_tier"]
    list_select_related = ["ritual", "item_template", "min_quality_tier"]


class ThreadLevelUnlockInline(admin.TabularInline):
    model = ThreadLevelUnlock
    extra = 0
    readonly_fields = ["acquired_at"]


@admin.register(Thread)
class ThreadAdmin(admin.ModelAdmin):
    list_display = ["id", "owner", "resonance", "target_kind", "level", "developed_points"]
    list_filter = ["target_kind", "resonance"]
    search_fields = ["owner__character__db_key", "resonance__name", "name"]
    autocomplete_fields = ["resonance"]
    raw_id_fields = [
        "owner",
        "target_trait",
        "target_technique",
        "target_relationship_track",
        "target_capstone",
    ]
    list_select_related = ["owner", "resonance"]
    readonly_fields = ["created_at", "updated_at"]
    inlines = [ThreadLevelUnlockInline]


@admin.register(ThreadLevelUnlock)
class ThreadLevelUnlockAdmin(admin.ModelAdmin):
    list_display = ["thread", "unlocked_level", "xp_spent", "acquired_at"]
    list_filter = ["unlocked_level"]
    search_fields = ["thread__owner__character__db_key"]
    readonly_fields = ["acquired_at"]
    raw_id_fields = ["thread"]


@admin.register(ThreadWeavingUnlock)
class ThreadWeavingUnlockAdmin(admin.ModelAdmin):
    list_display = ["id", "target_kind", "display_name", "xp_cost", "out_of_path_multiplier"]
    list_filter = ["target_kind"]
    search_fields = [
        "unlock_trait__name",
        "unlock_gift__name",
        "unlock_track__name",
    ]
    raw_id_fields = [
        "unlock_trait",
        "unlock_gift",
        "unlock_track",
    ]
    filter_horizontal = ["paths"]


@admin.register(CharacterThreadWeavingUnlock)
class CharacterThreadWeavingUnlockAdmin(admin.ModelAdmin):
    list_display = ["id", "character", "unlock", "xp_spent", "teacher", "acquired_at"]
    list_filter = ["unlock__target_kind"]
    search_fields = [
        "character__character__db_key",
        "unlock__unlock_trait__name",
        "unlock__unlock_gift__name",
    ]
    raw_id_fields = ["character", "unlock", "teacher"]
    readonly_fields = ["acquired_at"]


@admin.register(ThreadWeavingTeachingOffer)
class ThreadWeavingTeachingOfferAdmin(admin.ModelAdmin):
    list_display = ["id", "teacher", "unlock", "gold_cost", "banked_ap", "created_at"]
    list_filter = ["unlock__target_kind"]
    search_fields = [
        "teacher__roster_entry__character__db_key",
        "unlock__unlock_trait__name",
        "unlock__unlock_gift__name",
        "pitch",
    ]
    raw_id_fields = ["teacher", "unlock"]
    readonly_fields = ["created_at"]


@admin.register(ResonanceGrant)
class ResonanceGrantAdmin(admin.ModelAdmin):
    autocomplete_fields = ["character_sheet", "source_staff_account"]
    list_display = (
        "id",
        "character_sheet",
        "resonance",
        "amount",
        "source",
        "granted_at",
    )
    list_filter = ("source", "resonance")
    search_fields = ("character_sheet__id",)
    readonly_fields = (
        "character_sheet",
        "resonance",
        "amount",
        "source",
        "granted_at",
        "source_room_profile",
        "source_staff_account",
        "source_pose_endorsement",
        "source_scene_entry_endorsement",
    )

    def has_add_permission(self, request) -> bool:  # noqa: ARG002
        return False

    def has_change_permission(self, request, obj=None) -> bool:  # noqa: ARG002
        return False

    def has_delete_permission(self, request, obj=None) -> bool:  # noqa: ARG002
        return False


@admin.register(PoseEndorsement)
class PoseEndorsementAdmin(admin.ModelAdmin):
    autocomplete_fields = ["endorsee_sheet", "endorser_sheet", "interaction", "persona_snapshot"]
    list_display = (
        "id",
        "endorser_sheet",
        "endorsee_sheet",
        "resonance",
        "created_at",
        "settled_at",
    )
    list_filter = ("settled_at",)
    readonly_fields = tuple(f.name for f in PoseEndorsement._meta.fields)  # noqa: SLF001

    def has_add_permission(self, request) -> bool:  # noqa: ARG002
        return False

    def has_change_permission(self, request, obj=None) -> bool:  # noqa: ARG002
        return False


@admin.register(SceneEntryEndorsement)
class SceneEntryEndorsementAdmin(admin.ModelAdmin):
    autocomplete_fields = [
        "endorsee_sheet",
        "endorser_sheet",
        "entry_interaction",
        "persona_snapshot",
        "scene",
    ]
    list_display = (
        "id",
        "endorser_sheet",
        "endorsee_sheet",
        "scene",
        "resonance",
        "created_at",
        "granted_amount",
    )
    readonly_fields = tuple(f.name for f in SceneEntryEndorsement._meta.fields)  # noqa: SLF001

    def has_add_permission(self, request) -> bool:  # noqa: ARG002
        return False

    def has_change_permission(self, request, obj=None) -> bool:  # noqa: ARG002
        return False


@admin.register(MagicProgressionMilestone)
class MagicProgressionMilestoneAdmin(admin.ModelAdmin):
    list_display = ("stage", "kind", "codex_entry", "sort_order")
    list_filter = ("stage", "kind")
    autocomplete_fields = ("codex_entry",)


@admin.register(RelationshipBondPullTuning)
class RelationshipBondPullTuningAdmin(admin.ModelAdmin):
    """Singleton tuning config for relationship-bond thread-pull modulation (#1849)
    plus the fraught/devotion differential terms (#2034)."""

    list_display = (
        "pk",
        "coefficient",
        "cap",
        "half_saturation",
        "fraught_coefficient",
        "fraught_cap",
        "fraught_half_saturation",
        "devotion_threshold",
        "devotion_coefficient",
        "devotion_cap",
        "devotion_half_saturation",
    )

    def has_add_permission(self, request) -> bool:  # noqa: ARG002
        return not RelationshipBondPullTuning.objects.exists()

    def has_delete_permission(self, request, obj=None) -> bool:  # noqa: ARG002
        return False


@admin.register(SoulTetherConfig)
class SoulTetherConfigAdmin(admin.ModelAdmin):
    """Singleton tuning config for the Soul Tether bond mechanic — one row per environment."""

    autocomplete_fields = ["updated_by"]

    list_display = (
        "pk",
        "anima_cost_per_unit",
        "fatigue_cost_per_unit",
        "per_scene_cap_hard_max",
        "rescue_strain_stage3",
        "rescue_strain_stage4",
        "rescue_strain_stage5",
        "updated_at",
    )

    def has_add_permission(self, request) -> bool:  # noqa: ARG002
        return not SoulTetherConfig.objects.exists()

    def has_delete_permission(self, request, obj=None) -> bool:  # noqa: ARG002
        return False


@admin.register(TouchstoneCastConfig)
class TouchstoneCastConfigAdmin(admin.ModelAdmin):
    """Singleton tuning config for touchstone combat resonance (#2023)."""

    list_display = ("pk", "config_scale")

    def has_add_permission(self, request) -> bool:  # noqa: ARG002
        return not TouchstoneCastConfig.objects.exists()

    def has_delete_permission(self, request, obj=None) -> bool:  # noqa: ARG002
        return False


@admin.register(DramaticMomentType)
class DramaticMomentTypeAdmin(admin.ModelAdmin):
    list_display = ("label", "resonance", "resonance_amount", "per_scene_cap", "magnitude", "risk")
    search_fields = ("label", "description")
    list_filter = ("magnitude", "risk")
    filter_horizontal = ("archetypes",)


@admin.register(DramaticMomentTag)
class DramaticMomentTagAdmin(admin.ModelAdmin):
    autocomplete_fields = ["character_sheet", "interaction", "scene", "tagged_by"]
    list_display = ("id", "character_sheet", "moment_type", "scene", "tagged_by", "tagged_at")
    list_filter = ("moment_type",)
    readonly_fields = tuple(f.name for f in DramaticMomentTag._meta.fields)  # noqa: SLF001

    def has_add_permission(self, request) -> bool:  # noqa: ARG002
        return False

    def has_change_permission(self, request, obj=None) -> bool:  # noqa: ARG002
        return False


@admin.register(DramaticMomentSuggestion)
class DramaticMomentSuggestionAdmin(admin.ModelAdmin):
    autocomplete_fields = ["character_sheet", "interaction", "resolved_by", "scene"]
    list_display = (
        "id",
        "character_sheet",
        "moment_type",
        "scene",
        "status",
        "success_level",
        "resolved_by",
        "created_at",
    )
    list_filter = ("status", "moment_type")
    readonly_fields = tuple(f.name for f in DramaticMomentSuggestion._meta.fields)  # noqa: SLF001

    def has_add_permission(self, request) -> bool:  # noqa: ARG002
        # Suggestions are only ever created by maybe_suggest_dramatic_moments() and
        # resolved via resolve_dramatic_moment_suggestion() — no admin-authored rows.
        return False

    def has_change_permission(self, request, obj=None) -> bool:  # noqa: ARG002
        return False


@admin.register(GiftUnlock)
class GiftUnlockAdmin(admin.ModelAdmin):
    list_display = ["gift", "xp_cost", "out_of_path_multiplier"]
    list_filter = ["paths"]
    search_fields = ["gift__name"]
    filter_horizontal = ["paths"]


@admin.register(CharacterGiftUnlock)
class CharacterGiftUnlockAdmin(admin.ModelAdmin):
    autocomplete_fields = ["character", "teacher"]
    list_display = ["character", "unlock", "xp_spent", "teacher", "acquired_at"]
    search_fields = ["character__name"]
    readonly_fields = ["acquired_at"]


@admin.register(TechniqueTeachingOffer)
class TechniqueTeachingOfferAdmin(admin.ModelAdmin):
    autocomplete_fields = ["teacher"]
    list_display = [
        "teacher",
        "technique",
        "learn_ap_cost",
        "gold_cost",
        "banked_ap",
    ]
    search_fields = ["teacher__character__name", "technique__name"]


@admin.register(GiftAcquisitionConfig)
class GiftAcquisitionConfigAdmin(admin.ModelAdmin):
    list_display = [
        "techniques_per_thread_level",
        "first_technique_ap_multiplier",
        "major_gift_ap_multiplier",
    ]


@admin.register(TechniqueGrant)
class TechniqueGrantAdmin(admin.ModelAdmin):
    list_display = ["technique", "item_template", "ritual", "verb", "acquisition_ap_cost"]
    list_filter = ["verb"]
    autocomplete_fields = ["technique", "item_template", "ritual"]


class SignatureMotifBonusCapabilityGrantInline(admin.TabularInline):
    """Capability-grant payload rows for a SignatureMotifBonus.

    WARNING: these rows are currently INERT. There is no technique-capability-grant
    cast seam (combat or non-combat) that reads a SignatureMotifBonus's capability
    grants — authoring a row here has no in-game effect yet.
    """

    model = SignatureMotifBonusCapabilityGrant
    extra = 0
    autocomplete_fields = ["capability"]
    verbose_name = "Capability Grant (INERT — not applied at cast time)"
    verbose_name_plural = "Capability Grants (INERT — not applied at cast time)"


class SignatureMotifBonusDamageProfileInline(admin.TabularInline):
    """Damage-profile payload rows for a SignatureMotifBonus.

    NOTE: applied in COMBAT casts only. A standalone (non-combat) cast of a
    technique carrying a signed bonus deals no damage from these rows.
    """

    model = SignatureMotifBonusDamageProfile
    extra = 0
    autocomplete_fields = ["damage_type"]
    verbose_name = "Damage Profile (combat casts only)"
    verbose_name_plural = "Damage Profiles (combat casts only)"


class SignatureMotifBonusAppliedConditionInline(admin.TabularInline):
    """Applied-condition payload rows for a SignatureMotifBonus.

    Fully wired on both cast paths (combat + non-combat) — no caveat needed.
    """

    model = SignatureMotifBonusAppliedCondition
    extra = 0
    autocomplete_fields = ["condition"]


@admin.register(SignatureMotifBonus)
class SignatureMotifBonusAdmin(admin.ModelAdmin):
    """Staff-authored, Motif-gated additive bonus signed onto a TECHNIQUE thread.

    Payload rows below carry differing wiring status — see each inline's help text
    before authoring: capability grants are inert (no cast seam yet); damage
    profiles apply in combat casts only; applied conditions are fully wired.
    """

    list_display = [
        "name",
        "required_facet",
        "required_resonance",
        "flat_intensity_delta",
        "min_crossing_level",
    ]
    list_filter = ["required_facet", "required_resonance", "min_crossing_level"]
    search_fields = ["name", "narrative_snippet"]
    autocomplete_fields = [
        "required_facet",
        "required_resonance",
        "discovery_achievement",
    ]
    inlines = [
        SignatureMotifBonusCapabilityGrantInline,
        SignatureMotifBonusDamageProfileInline,
        SignatureMotifBonusAppliedConditionInline,
    ]


# =============================================================================
# Trait crossing admin (#1989)
# =============================================================================


@admin.register(CrossingOption)
class CrossingOptionAdmin(admin.ModelAdmin):
    """Admin for the authored crossing option catalog."""

    list_display = (
        "name",
        "target_kind",
        "resonance",
        "crossing_level",
        "is_default",
    )
    list_filter = ("target_kind", "is_default", "crossing_level")
    search_fields = ("name", "description")
    autocomplete_fields = (
        "resonance",
        "condition_template",
        "discovery_achievement",
        "codex_entry",
    )


@admin.register(CrossingChoice)
class CrossingChoiceAdmin(admin.ModelAdmin):
    """Read-only admin for trait crossing choice receipts (provenance audit)."""

    list_display = ("thread", "crossing_level", "option", "chosen_at")
    list_filter = ("crossing_level",)
    readonly_fields = ("thread", "crossing_level", "option", "chosen_at")

    def has_add_permission(self, request):  # noqa: ARG002
        return False

    def has_change_permission(self, request, obj=None):  # noqa: ARG002
        return False


# ---------------------------------------------------------------------------
# #1583 — Fall / Redemption
# ---------------------------------------------------------------------------


@admin.register(CompromiseActType)
class CompromiseActTypeAdmin(admin.ModelAdmin):
    """Admin for authored compromise act types."""

    list_display = ("name", "target_resonance", "amount", "is_cruelty")
    list_filter = ("is_cruelty",)
    search_fields = ("name", "description")


from world.magic.models import (  # noqa: E402
    FallRedemptionConfig,
    FallRedemptionRecord,
    GhostTutelage,
    ResonanceConversion,
)


@admin.register(ResonanceConversion)
class ResonanceConversionAdmin(admin.ModelAdmin):
    """Admin for resonance conversion mappings."""

    list_display = ("source_resonance", "target_affinity", "target_resonance")
    search_fields = (
        "source_resonance__name",
        "target_resonance__name",
    )


@admin.register(FallRedemptionConfig)
class FallRedemptionConfigAdmin(admin.ModelAdmin):
    """Admin for the Fall/Redemption tuning singleton."""

    list_display = ("id", "celestial_to_primal_multiplier", "celestial_to_abyssal_multiplier")


@admin.register(FallRedemptionRecord)
class FallRedemptionRecordAdmin(admin.ModelAdmin):
    """Read-only admin for Fall/Redemption conversion audit records."""

    autocomplete_fields = ["character_sheet", "scene"]

    list_display = (
        "character_sheet",
        "conversion_type",
        "from_affinity",
        "to_affinity",
        "performed_at",
    )
    list_filter = ("conversion_type", "from_affinity", "to_affinity")
    readonly_fields = (
        "character_sheet",
        "conversion_type",
        "from_affinity",
        "to_affinity",
        "multiplier",
        "performed_at",
        "scene",
    )

    def has_add_permission(self, request):  # noqa: ARG002
        return False

    def has_change_permission(self, request, obj=None):  # noqa: ARG002
        return False


@admin.register(GhostTutelage)
class GhostTutelageAdmin(admin.ModelAdmin):
    """Admin for ghost-tutelage records (#2460)."""

    list_display = ("character_sheet", "tradition", "created_at")
    list_filter = ("tradition",)
    search_fields = ("character_sheet__roster_entry__character__db_key",)
    readonly_fields = ("created_at",)
    autocomplete_fields = ("character_sheet",)
