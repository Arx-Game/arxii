from django.contrib import admin

from world.worship.models import (
    BeingFacet,
    BeingNickname,
    BeingRelationship,
    BeingResonance,
    ChosenFavorConfig,
    DevotionStanding,
    DivineInterventionConfig,
    Miracle,
    MiracleAppliedCondition,
    MiracleDamageProfile,
    MiraclePerformance,
    Relic,
    RiteKind,
    WorshipDeclaration,
    WorshipFeastDay,
    WorshipGrant,
    WorshippedBeing,
    WorshipRite,
    WorshipRitePerformance,
    WorshipRiteTierAward,
    WorshipTradition,
)


@admin.register(WorshipTradition)
class WorshipTraditionAdmin(admin.ModelAdmin):
    list_display = ("name", "rites_specialization")
    search_fields = ("name",)


@admin.register(WorshippedBeing)
class WorshippedBeingAdmin(admin.ModelAdmin):
    list_display = ("name", "tradition", "resonance_pool", "lifetime_worship", "is_active")
    list_filter = ("tradition", "is_active")
    search_fields = ("name",)
    raw_id_fields = ("avatar_sheet",)
    # codex_entry points into the whole CodexEntry corpus — a plain select would
    # render every entry. Same widget MagicProgressionMilestoneAdmin uses against
    # the same CodexEntryAdmin (which declares the required search_fields).
    autocomplete_fields = ("codex_entry",)
    # 78 tarot cards: too many for a scrolling multi-select, too few to search.
    filter_horizontal = ("tarot_cards",)


@admin.register(BeingFacet)
class BeingFacetAdmin(admin.ModelAdmin):
    list_display = ("being", "facet")
    list_filter = ("being",)
    search_fields = ("being__name", "facet__name")


@admin.register(BeingResonance)
class BeingResonanceAdmin(admin.ModelAdmin):
    list_display = ("being", "resonance", "tier")
    list_filter = ("being", "tier")
    search_fields = ("being__name", "resonance__name")


@admin.register(BeingNickname)
class BeingNicknameAdmin(admin.ModelAdmin):
    list_display = ("name", "being")
    list_filter = ("being",)
    search_fields = ("being__name", "name")


@admin.register(BeingRelationship)
class BeingRelationshipAdmin(admin.ModelAdmin):
    list_display = ("being_a", "being_b", "valence")
    list_filter = ("valence",)
    search_fields = ("being_a__name", "being_b__name")


@admin.register(WorshipFeastDay)
class WorshipFeastDayAdmin(admin.ModelAdmin):
    list_display = ("name", "being", "ic_month", "ic_day")
    list_filter = ("being",)
    search_fields = ("name", "being__name")


@admin.register(WorshipGrant)
class WorshipGrantAdmin(admin.ModelAdmin):
    list_display = ("being", "amount", "granted_by", "reason", "created_at")
    list_filter = ("being",)
    raw_id_fields = ("granted_by",)


@admin.register(DevotionStanding)
class DevotionStandingAdmin(admin.ModelAdmin):
    list_display = (
        "character_sheet",
        "being",
        "favor",
        "lifetime_favor",
        "valence",
        "established_at",
        "released_at",
    )
    list_filter = ("being", "valence")
    raw_id_fields = ("character_sheet",)


@admin.register(WorshipDeclaration)
class WorshipDeclarationAdmin(admin.ModelAdmin):
    list_display = ("character_sheet", "public_being", "secret_being")
    raw_id_fields = ("character_sheet", "secret")


class MiracleAppliedConditionInline(admin.TabularInline):
    model = MiracleAppliedCondition
    extra = 0


class MiracleDamageProfileInline(admin.TabularInline):
    model = MiracleDamageProfile
    extra = 0


@admin.register(Miracle)
class MiracleAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "being",
        "resonance_pool_cost",
        "intervention_trigger",
        "favor_threshold",
        "is_active",
    )
    list_filter = ("being", "intervention_trigger", "is_active")
    search_fields = ("name",)
    inlines = [
        MiracleAppliedConditionInline,
        MiracleDamageProfileInline,
    ]


@admin.register(MiraclePerformance)
class MiraclePerformanceAdmin(admin.ModelAdmin):
    list_display = (
        "miracle",
        "being",
        "target_character",
        "resonance_spent",
        "trigger_event",
        "created_at",
    )
    list_filter = ("being", "trigger_event")
    raw_id_fields = ("target_character", "scene")
    readonly_fields = (
        "miracle",
        "being",
        "target_character",
        "scene",
        "resonance_spent",
        "trigger_event",
        "created_at",
    )


@admin.register(DivineInterventionConfig)
class DivineInterventionConfigAdmin(admin.ModelAdmin):
    list_display = ("favor_threshold", "cooldown_hours", "min_pool_for_intervention")


@admin.register(ChosenFavorConfig)
class ChosenFavorConfigAdmin(admin.ModelAdmin):
    list_display = ("id", "anima_recovery_threshold", "anima_recovery_bonus")


@admin.register(RiteKind)
class RiteKindAdmin(admin.ModelAdmin):
    list_display = ("name", "tier")
    list_filter = ("tier",)
    search_fields = ("name",)


@admin.register(WorshipRite)
class WorshipRiteAdmin(admin.ModelAdmin):
    list_display = ("name", "being", "kind", "check_type", "resonance", "is_active")
    list_filter = ("kind__tier", "is_active")
    search_fields = ("name", "being__name")
    autocomplete_fields = ("being", "check_type")
    raw_id_fields = ("resonance",)


@admin.register(WorshipRiteTierAward)
class WorshipRiteTierAwardAdmin(admin.ModelAdmin):
    list_display = ("tier", "outcome_tier", "resonance_amount", "favor_amount")
    list_filter = ("tier",)


@admin.register(WorshipRitePerformance)
class WorshipRitePerformanceAdmin(admin.ModelAdmin):
    list_display = (
        "character_sheet",
        "rite",
        "outcome_tier",
        "resonance_granted",
        "favor_granted",
        "performed_at",
    )
    list_filter = ("rite__kind__tier",)
    raw_id_fields = ("character_sheet", "rite", "game_week", "scene", "ceremony")


@admin.register(Relic)
class RelicAdmin(admin.ModelAdmin):
    list_display = ("item_instance", "being", "created_at")
    search_fields = ("being__name", "item_instance__custom_name", "item_instance__template__name")
    autocomplete_fields = ("being",)
    raw_id_fields = ("item_instance",)
