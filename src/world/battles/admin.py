"""Django admin for the battles app (#1711).

The shipped spine (#1592) had zero admin exposure — this fixes that gap and
gives staff a CRUD surface for the new authored catalogs (#1711).
"""

from __future__ import annotations

from django.contrib import admin

from world.battles.models import (
    Battle,
    BattleActionDeclaration,
    BattleOutcomeMapping,
    BattleParticipant,
    BattlePlace,
    BattleRound,
    BattleSide,
    BattleUnit,
    BattleUnitCapability,
    Fortification,
    TechniquePropertyAffinity,
    TerrainPropertyEffect,
)


@admin.register(Battle)
class BattleAdmin(admin.ModelAdmin):
    list_display = ("name", "outcome", "round_limit", "created_at")
    list_filter = ("outcome",)
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


class BattleUnitCapabilityInline(admin.TabularInline):
    model = BattleUnitCapability
    extra = 0
    autocomplete_fields = ("capability",)


@admin.register(BattleUnit)
class BattleUnitAdmin(admin.ModelAdmin):
    list_display = (
        "battle",
        "name",
        "quality",
        "commander",
        "strength",
        "morale",
        "status",
    )
    list_filter = ("quality", "status")
    search_fields = ("name", "descriptor")
    autocomplete_fields = ("commander", "summoned_by")
    filter_horizontal = ("properties",)
    inlines = [BattleUnitCapabilityInline]


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


@admin.register(BattleOutcomeMapping)
class BattleOutcomeMappingAdmin(admin.ModelAdmin):
    list_display = ["outcome", "check_outcome"]
    list_filter = ["outcome"]
