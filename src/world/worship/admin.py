from django.contrib import admin

from world.worship.models import (
    DevotionStanding,
    DivineInterventionConfig,
    Miracle,
    MiracleAppliedCondition,
    MiracleCapabilityGrant,
    MiracleDamageProfile,
    MiraclePerformance,
    WorshipDeclaration,
    WorshipGrant,
    WorshippedBeing,
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


@admin.register(WorshipGrant)
class WorshipGrantAdmin(admin.ModelAdmin):
    list_display = ("being", "amount", "granted_by", "reason", "created_at")
    list_filter = ("being",)
    raw_id_fields = ("granted_by",)


@admin.register(DevotionStanding)
class DevotionStandingAdmin(admin.ModelAdmin):
    list_display = ("character_sheet", "being", "favor", "lifetime_favor")
    list_filter = ("being",)
    raw_id_fields = ("character_sheet",)


@admin.register(WorshipDeclaration)
class WorshipDeclarationAdmin(admin.ModelAdmin):
    list_display = ("character_sheet", "public_being", "secret_being")
    raw_id_fields = ("character_sheet", "secret")


class MiracleCapabilityGrantInline(admin.TabularInline):
    model = MiracleCapabilityGrant
    extra = 0


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
        MiracleCapabilityGrantInline,
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
