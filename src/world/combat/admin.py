"""Django admin configuration for the combat system."""

from django.contrib import admin

from world.combat.models import (
    BossPhase,
    CombatEncounter,
    CombatOpponent,
    CombatOpponentAction,
    CombatParticipant,
    CombatRoundAction,
    ThreatPool,
    ThreatPoolEntry,
)


class CombatOpponentInline(admin.TabularInline):
    model = CombatOpponent
    extra = 0
    fields = ["name", "tier", "health", "max_health", "status", "threat_pool"]


class CombatParticipantInline(admin.TabularInline):
    model = CombatParticipant
    extra = 0
    raw_id_fields = ["covenant_role"]
    fields = [
        "character_sheet",
        "covenant_role",
        "base_speed_rank",
        "health",
        "max_health",
        "status",
    ]


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
    list_display = [
        "character_sheet",
        "encounter",
        "covenant_role",
        "base_speed_rank",
        "health",
        "max_health",
        "status",
    ]
    list_filter = ["status"]
    autocomplete_fields = ["covenant_role"]


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
