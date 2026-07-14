"""Django admin for the battles app (#1711).

The shipped spine (#1592) had zero admin exposure — this fixes that gap and
gives staff a CRUD surface for the new authored catalogs (#1711).
"""

from __future__ import annotations

from django.contrib import admin

from world.battles.models import (
    Battle,
    BattleActionDeclaration,
    BattleMapBlueprint,
    BattleOutcomeMapping,
    BattleParticipant,
    BattlePlace,
    BattleRound,
    BattleSide,
    BattleUnit,
    BattleUnitTemplate,
    BattleUnitTemplateCapability,
    BlueprintBattlePlace,
    BlueprintFortification,
    CityDefenseDetails,
    CityDefenseIntegrityBonus,
    CityDefenseTierThreshold,
    Fortification,
    TechniquePropertyAffinity,
    TerrainPropertyEffect,
    WeatherTypeCapabilityChallenge,
    WeatherTypePropertyEffect,
)


@admin.register(Battle)
class BattleAdmin(admin.ModelAdmin):
    list_display = ("name", "outcome", "round_limit", "risk_level", "created_at")
    list_filter = ("outcome", "risk_level")
    search_fields = ("name",)


@admin.register(BattleSide)
class BattleSideAdmin(admin.ModelAdmin):
    list_display = ("battle", "role", "posture", "victory_points", "victory_threshold")
    list_filter = ("role", "posture")
    search_fields = ("battle__name",)


@admin.register(BattlePlace)
class BattlePlaceAdmin(admin.ModelAdmin):
    list_display = ("battle", "name", "terrain_type", "movement_cost", "controlled_by")
    list_filter = ("terrain_type",)
    autocomplete_fields = ("controlled_by",)


@admin.register(Fortification)
class FortificationAdmin(admin.ModelAdmin):
    list_display = ("place", "kind", "defending_side", "integrity", "max_integrity", "breached")
    list_filter = ("kind", "breached")


@admin.register(BattleUnit)
class BattleUnitAdmin(admin.ModelAdmin):
    list_display = (
        "battle",
        "military_unit",
        "status",
    )
    list_filter = ("status",)
    search_fields = ("military_unit__name", "military_unit__descriptor")
    autocomplete_fields = ("military_unit",)


@admin.register(BattleRound)
class BattleRoundAdmin(admin.ModelAdmin):
    list_display = ("battle", "round_number", "status")
    list_filter = ("status",)


@admin.register(BattleParticipant)
class BattleParticipantAdmin(admin.ModelAdmin):
    list_display = ("battle", "character_sheet", "side", "place", "status")
    list_filter = ("status",)


@admin.register(BattleActionDeclaration)
class BattleActionDeclarationAdmin(admin.ModelAdmin):
    list_display = ("battle_round", "participant", "action_kind", "resolved", "success_level")
    list_filter = ("action_kind", "resolved")


@admin.register(TechniquePropertyAffinity)
class TechniquePropertyAffinityAdmin(admin.ModelAdmin):
    list_display = ("technique", "property", "modifier")
    list_filter = ("property",)
    autocomplete_fields = ("technique", "property")


@admin.register(TerrainPropertyEffect)
class TerrainPropertyEffectAdmin(admin.ModelAdmin):
    list_display = ("terrain_type", "property", "modifier")
    list_filter = ("terrain_type", "property")
    autocomplete_fields = ("property",)


@admin.register(WeatherTypePropertyEffect)
class WeatherTypePropertyEffectAdmin(admin.ModelAdmin):
    list_display = ("weather_type", "property", "modifier")
    list_filter = ("weather_type", "property")
    autocomplete_fields = ("weather_type", "property")


@admin.register(WeatherTypeCapabilityChallenge)
class WeatherTypeCapabilityChallengeAdmin(admin.ModelAdmin):
    list_display = ("weather_type", "capability", "threshold", "modifier")
    list_filter = ("weather_type", "capability")
    autocomplete_fields = ("weather_type", "capability")


@admin.register(BattleOutcomeMapping)
class BattleOutcomeMappingAdmin(admin.ModelAdmin):
    list_display = ["outcome", "check_outcome"]
    list_filter = ["outcome"]


class BlueprintBattlePlaceInline(admin.TabularInline):
    model = BlueprintBattlePlace
    extra = 0


@admin.register(BattleMapBlueprint)
class BattleMapBlueprintAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)
    inlines = [BlueprintBattlePlaceInline]


@admin.register(BlueprintFortification)
class BlueprintFortificationAdmin(admin.ModelAdmin):
    list_display = ("blueprint_place", "kind", "defending_side_role", "max_integrity")
    list_filter = ("kind", "defending_side_role")
    raw_id_fields = ("blueprint_place",)


class BattleUnitTemplateCapabilityInline(admin.TabularInline):
    model = BattleUnitTemplateCapability
    extra = 0
    autocomplete_fields = ("capability",)


@admin.register(BattleUnitTemplate)
class BattleUnitTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "quality", "strength", "morale", "is_active")
    list_filter = ("quality", "is_active")
    search_fields = ("name", "descriptor")
    filter_horizontal = ("properties",)
    inlines = [BattleUnitTemplateCapabilityInline]


class CityDefenseTierThresholdInline(admin.TabularInline):
    model = CityDefenseTierThreshold
    extra = 0
    raw_id_fields = ("outcome_tier",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("outcome_tier")


@admin.register(CityDefenseDetails)
class CityDefenseDetailsAdmin(admin.ModelAdmin):
    list_display = ("project", "area", "outcome_tier", "applied_at")
    raw_id_fields = ("project", "area", "outcome_tier")
    search_fields = ("project__description",)
    inlines = [CityDefenseTierThresholdInline]


@admin.register(CityDefenseIntegrityBonus)
class CityDefenseIntegrityBonusAdmin(admin.ModelAdmin):
    list_display = ("outcome_tier", "integrity_bonus")
    raw_id_fields = ("outcome_tier",)
    ordering = ("-outcome_tier__success_level",)
