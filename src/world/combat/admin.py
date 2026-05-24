"""Django admin configuration for the combat system."""

from django.contrib import admin

from world.combat.models import (
    BossPhase,
    Clash,
    ClashConfig,
    ClashContribution,
    ClashRound,
    CombatEncounter,
    CombatOpponent,
    CombatOpponentAction,
    CombatParticipant,
    CombatPull,
    CombatPullResolvedEffect,
    CombatRoundAction,
    ComboDefinition,
    ComboLearning,
    ComboSlot,
    StrainConfig,
    ThreatPool,
    ThreatPoolEntry,
)


class CombatOpponentInline(admin.TabularInline):
    model = CombatOpponent
    extra = 0
    fields = ["name", "persona", "tier", "health", "max_health", "status", "threat_pool"]


class CombatParticipantInline(admin.TabularInline):
    model = CombatParticipant
    extra = 0
    raw_id_fields = ["covenant_role"]
    fields = ["character_sheet", "covenant_role"]


@admin.register(CombatEncounter)
class CombatEncounterAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "encounter_type",
        "round_number",
        "status",
        "risk_level",
        "stakes_level",
        "created_at",
    ]
    list_filter = ["encounter_type", "status", "risk_level", "stakes_level"]
    inlines = [CombatOpponentInline, CombatParticipantInline]


class BossPhaseInline(admin.TabularInline):
    model = BossPhase
    extra = 0
    fields = [
        "phase_number",
        "threat_pool",
        "soak_value",
        "probing_threshold",
        "health_trigger_percentage",
    ]


@admin.register(CombatOpponent)
class CombatOpponentAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "persona",
        "encounter",
        "tier",
        "health",
        "max_health",
        "status",
    ]
    list_filter = ["tier", "status"]
    inlines = [BossPhaseInline]


@admin.register(CombatParticipant)
class CombatParticipantAdmin(admin.ModelAdmin):
    list_display = ["character_sheet", "encounter", "covenant_role"]


class ThreatPoolEntryInline(admin.TabularInline):
    model = ThreatPoolEntry
    extra = 0
    fields = [
        "name",
        "attack_category",
        "base_damage",
        "weight",
        "targeting_mode",
    ]


@admin.register(ThreatPool)
class ThreatPoolAdmin(admin.ModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]
    inlines = [ThreatPoolEntryInline]


@admin.register(ThreatPoolEntry)
class ThreatPoolEntryAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "pool",
        "attack_category",
        "base_damage",
        "weight",
        "targeting_mode",
    ]
    list_filter = ["attack_category", "targeting_mode", "target_selection"]


@admin.register(BossPhase)
class BossPhaseAdmin(admin.ModelAdmin):
    list_display = [
        "opponent",
        "phase_number",
        "soak_value",
        "probing_threshold",
        "health_trigger_percentage",
    ]


@admin.register(CombatRoundAction)
class CombatRoundActionAdmin(admin.ModelAdmin):
    list_display = [
        "participant",
        "round_number",
        "focused_category",
        "effort_level",
    ]
    list_filter = ["focused_category", "effort_level"]


@admin.register(CombatOpponentAction)
class CombatOpponentActionAdmin(admin.ModelAdmin):
    list_display = ["opponent", "round_number", "threat_entry"]


class ComboSlotInline(admin.TabularInline):
    model = ComboSlot
    extra = 0
    fields = ["slot_number", "required_action_type", "resonance_requirement"]


@admin.register(ComboDefinition)
class ComboDefinitionAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "slug",
        "hidden",
        "bypass_soak",
        "bonus_damage",
        "minimum_probing",
    ]
    list_filter = ["hidden", "bypass_soak"]
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ComboSlotInline]


@admin.register(ComboSlot)
class ComboSlotAdmin(admin.ModelAdmin):
    list_display = ["combo", "slot_number", "required_action_type", "resonance_requirement"]
    list_filter = ["required_action_type"]


@admin.register(ComboLearning)
class ComboLearningAdmin(admin.ModelAdmin):
    list_display = ["character_sheet", "combo", "learned_via", "learned_at"]
    list_filter = ["learned_via"]


class CombatPullResolvedEffectInline(admin.TabularInline):
    model = CombatPullResolvedEffect
    extra = 0
    fields = [
        "kind",
        "authored_value",
        "level_multiplier",
        "scaled_value",
        "vital_target",
        "source_thread",
        "source_thread_level",
        "source_tier",
        "granted_capability",
        "narrative_snippet",
    ]
    raw_id_fields = ["source_thread", "granted_capability"]


@admin.register(CombatPull)
class CombatPullAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "participant",
        "encounter",
        "round_number",
        "resonance",
        "tier",
        "resonance_spent",
        "anima_spent",
        "committed_at",
    ]
    list_filter = ["tier", "resonance"]
    search_fields = [
        "participant__character_sheet__display_name",
        "encounter__id",
    ]
    raw_id_fields = ["participant", "encounter", "resonance", "threads"]
    inlines = [CombatPullResolvedEffectInline]


@admin.register(CombatPullResolvedEffect)
class CombatPullResolvedEffectAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "pull",
        "kind",
        "scaled_value",
        "vital_target",
        "source_thread",
        "source_tier",
        "granted_capability",
    ]
    list_filter = ["kind", "vital_target", "source_tier"]
    search_fields = ["narrative_snippet"]
    raw_id_fields = ["pull", "source_thread", "granted_capability"]


# =============================================================================
# Clash admin (Task 1.7)
# =============================================================================


class ClashContributionInline(admin.TabularInline):
    model = ClashContribution
    extra = 0
    fields = [
        "character",
        "action_slot",
        "anima_committed",
        "check_outcome",
        "progress_delta",
        "was_overburn",
        "was_audere",
        "soulfray_severity_accrued",
    ]
    raw_id_fields = ["character", "check_outcome"]


class ClashRoundInline(admin.TabularInline):
    model = ClashRound
    extra = 0
    fields = [
        "round_number",
        "pc_progress_delta",
        "npc_progress_delta",
        "progress_after",
    ]


@admin.register(Clash)
class ClashAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "flavor",
        "encounter",
        "npc_opponent",
        "status",
        "progress",
        "pc_win_threshold",
        "npc_win_threshold",
        "started_round",
        "resolved_round",
        "resolution",
    ]
    list_filter = ["flavor", "status", "resolution"]
    raw_id_fields = [
        "encounter",
        "npc_opponent",
        "initiator",
        "resolution_consequence_pool",
        "per_round_consequence_pool",
    ]
    inlines = [ClashRoundInline]


@admin.register(ClashRound)
class ClashRoundAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "clash",
        "round_number",
        "pc_progress_delta",
        "npc_progress_delta",
        "progress_after",
    ]
    list_filter = ["clash__flavor"]
    raw_id_fields = ["clash"]
    inlines = [ClashContributionInline]


@admin.register(StrainConfig)
class StrainConfigAdmin(admin.ModelAdmin):
    list_display = [
        "pk",
        "conversion_base",
        "diminishing_step",
        "diminishing_floor",
        "updated_at",
    ]


@admin.register(ClashConfig)
class ClashConfigAdmin(admin.ModelAdmin):
    list_display = [
        "pk",
        "affinity_tilt_coefficient",
        "passive_anima_cap",
        "break_abandon_idle_rounds",
        "max_round_cap",
        "updated_at",
    ]
