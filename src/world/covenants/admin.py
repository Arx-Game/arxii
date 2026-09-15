"""Django admin configuration for the covenants system."""

from django.contrib import admin

from world.covenants.models import (
    CourtGrantConfig,
    Covenant,
    CovenantLevelBonus,
    CovenantLevelThreshold,
    CovenantRite,
    CovenantRiteRolePackage,
    CovenantRole,
    CovenantRoleActionScaling,
    CovenantRoleBonus,
    CovenantRoleDefenseProfile,
    CovenantRoleGiftGrant,
    CovenantRoleTechniqueSpecialty,
    GearArchetypeCompatibility,
    InsightTableEntry,
    MentorBondConfig,
    SecondaryVowConfig,
    VowSituationalPerk,
    VowSituationalPerkRung,
    VowSituationalPerkSituation,
    VowStatScaling,
    WeaknessPoolEntry,
)


class CovenantRoleTechniqueSpecialtyInline(admin.TabularInline):
    """Inline per-vow technique specialty rows on the CovenantRole admin (#2443)."""

    model = CovenantRoleTechniqueSpecialty
    extra = 1


class CovenantRoleDefenseProfileInline(admin.StackedInline):
    model = CovenantRoleDefenseProfile
    extra = 0


@admin.register(CovenantRole)
class CovenantRoleAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "slug",
        "covenant_type",
        "sword_weight",
        "shield_weight",
        "crown_weight",
        "speed_rank",
    ]
    list_filter = ["covenant_type"]
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}
    inlines = [CovenantRoleTechniqueSpecialtyInline, CovenantRoleDefenseProfileInline]


@admin.register(CovenantRoleActionScaling)
class CovenantRoleActionScalingAdmin(admin.ModelAdmin):
    list_display = ("action_key", "covenant_role", "thread_level_multiplier")
    list_filter = ("action_key",)
    autocomplete_fields = ("covenant_role",)


@admin.register(CovenantRoleTechniqueSpecialty)
class CovenantRoleTechniqueSpecialtyAdmin(admin.ModelAdmin):
    list_display = ("function", "covenant_role", "multiplier_tenths")
    list_filter = ("function",)
    autocomplete_fields = ("covenant_role",)


@admin.register(CovenantRoleDefenseProfile)
class CovenantRoleDefenseProfileAdmin(admin.ModelAdmin):
    list_display = ("covenant_role", "style", "gear_additive_tenths")
    list_filter = ("style",)
    autocomplete_fields = ("covenant_role",)


@admin.register(Covenant)
class CovenantAdmin(admin.ModelAdmin):
    autocomplete_fields = ["leader"]
    list_display = ("name", "covenant_type", "level", "formed_at", "dissolved_at")
    list_filter = ("covenant_type",)
    search_fields = ("name",)
    readonly_fields = ("formed_at", "provisioning_ratio")


@admin.register(CovenantLevelThreshold)
class CovenantLevelThresholdAdmin(admin.ModelAdmin):
    list_display = ("level", "required_legend")


@admin.register(CovenantRite)
class CovenantRiteAdmin(admin.ModelAdmin):
    list_display = (
        "ritual",
        "covenant_type",
        "min_covenant_level",
        "min_members_present",
        "granted_condition",
        "base_severity",
        "severity_per_extra_participant",
        "max_severity",
    )
    list_filter = ("covenant_type",)
    autocomplete_fields = ("ritual", "granted_condition")


@admin.register(CovenantRoleBonus)
class CovenantRoleBonusAdmin(admin.ModelAdmin):
    list_display = ("covenant_role", "modifier_target", "bonus_per_level")
    list_filter = ("covenant_role__covenant_type",)


@admin.register(CovenantLevelBonus)
class CovenantLevelBonusAdmin(admin.ModelAdmin):
    list_display = ("modifier_target", "bonus_per_level")


@admin.register(SecondaryVowConfig)
class SecondaryVowConfigAdmin(admin.ModelAdmin):
    """Singleton tuning config for the secondary-vow potency dial (#2641)."""

    list_display = ("pk", "potency_tenths", "updated_at", "updated_by")
    autocomplete_fields = ["updated_by"]

    def has_add_permission(self, request) -> bool:  # noqa: ARG002
        return not SecondaryVowConfig.objects.exists()

    def has_delete_permission(self, request, obj=None) -> bool:  # noqa: ARG002
        return False


class VowSituationalPerkSituationInline(admin.TabularInline):
    """Inline AND-composed situations on the perk admin (#2536)."""

    model = VowSituationalPerkSituation
    extra = 1


class VowSituationalPerkRungInline(admin.TabularInline):
    """Inline escalation rungs on the perk admin (#2536)."""

    model = VowSituationalPerkRung
    extra = 0


@admin.register(VowSituationalPerk)
class VowSituationalPerkAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "covenant_role",
        "effect_kind",
        "beneficiary",
        "magnitude_tenths",
        "floor_success_level",
        "battle_action_kind",
    )
    list_filter = ("effect_kind", "beneficiary")
    search_fields = ("name", "covenant_role__name")
    autocomplete_fields = ("covenant_role", "check_type")
    # mission_category/mission_template are NOT autocomplete_fields: the
    # missions app has no ModelAdmin registration (no world/missions/admin.py
    # exists) — Django's admin system check (E039) requires the related
    # model be registered with search_fields for autocomplete_fields to be
    # valid. raw_id_fields has no such registration requirement.
    raw_id_fields = ("mission_category", "mission_template")
    inlines = [VowSituationalPerkSituationInline, VowSituationalPerkRungInline]


@admin.register(WeaknessPoolEntry)
class WeaknessPoolEntryAdmin(admin.ModelAdmin):
    list_display = ("name", "creature_template", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "creature_template__name")
    raw_id_fields = ("creature_template", "condition")


# ---------------------------------------------------------------------------
# #3831
# ---------------------------------------------------------------------------


@admin.register(GearArchetypeCompatibility)
class GearArchetypeCompatibilityAdmin(admin.ModelAdmin):
    """#3831 - which covenant roles are compatible with which gear archetypes."""

    list_display = ("covenant_role", "gear_archetype")
    list_filter = ("gear_archetype",)
    search_fields = ("covenant_role__name",)
    autocomplete_fields = ("covenant_role",)


@admin.register(VowStatScaling)
class VowStatScalingAdmin(admin.ModelAdmin):
    """#3831 - authored vow-driven stat scaling per (covenant_role, modifier_target)."""

    list_display = ("covenant_role", "modifier_target", "bonus_per_level")
    search_fields = ("covenant_role__name", "modifier_target__name")
    autocomplete_fields = ("covenant_role", "modifier_target")


@admin.register(CovenantRoleGiftGrant)
class CovenantRoleGiftGrantAdmin(admin.ModelAdmin):
    """#3831 - the COVENANT_ROLE thread level at which a role's granted gift unlocks."""

    list_display = ("covenant_role", "gift", "unlock_thread_level")
    search_fields = ("covenant_role__name", "gift__name")
    autocomplete_fields = ("covenant_role", "gift")


@admin.register(CovenantRiteRolePackage)
class CovenantRiteRolePackageAdmin(admin.ModelAdmin):
    """#3831 - role- and level-gated stat package granted by a covenant rite."""

    list_display = ("rite", "covenant_role", "min_covenant_level", "condition_template")
    search_fields = ("covenant_role__name",)
    autocomplete_fields = ("covenant_role", "condition_template")


@admin.register(MentorBondConfig)
class MentorBondConfigAdmin(admin.ModelAdmin):
    """#3831 - the singleton Mentor's Vow bond scaling parameters (#1165)."""

    list_display = (
        "pk",
        "band_width",
        "adjacency_offset",
        "max_sidekicks_per_mentor",
        "updated_at",
    )
    autocomplete_fields = ["updated_by"]

    def has_add_permission(self, request: object) -> bool:  # noqa: ARG002
        """Prevent adding a second row; this is a pk=1 singleton."""
        return not MentorBondConfig.objects.exists()

    def has_delete_permission(
        self,
        request: object,  # noqa: ARG002
        obj: object = None,  # noqa: ARG002
    ) -> bool:
        """Prevent deleting the config."""
        return False


@admin.register(CourtGrantConfig)
class CourtGrantConfigAdmin(admin.ModelAdmin):
    """#3831 - the singleton Court grant negotiation tuning knobs (#1718)."""

    list_display = (
        "pk",
        "base_headroom",
        "affection_divisor",
        "mission_divisor",
        "updated_at",
    )
    autocomplete_fields = [
        "summons_refusal_escalation_pool",
        "petition_check_type",
        "escalation_consequence_pool",
    ]

    def has_add_permission(self, request: object) -> bool:  # noqa: ARG002
        """Prevent adding a second row; this is a pk=1 singleton."""
        return not CourtGrantConfig.objects.exists()

    def has_delete_permission(
        self,
        request: object,  # noqa: ARG002
        obj: object = None,  # noqa: ARG002
    ) -> bool:
        """Prevent deleting the config."""
        return False


@admin.register(InsightTableEntry)
class InsightTableEntryAdmin(admin.ModelAdmin):
    """#3831 - the curated Insight-table entries drawn at random (#2645)."""

    list_display = ("name", "condition", "target_kind", "weight", "is_active")
    list_filter = ("target_kind", "is_active")
    search_fields = ("name",)
    autocomplete_fields = ("condition",)
