"""Django admin for the battles app (#1711).

The shipped spine (#1592) had zero admin exposure — this fixes that gap and
gives staff a CRUD surface for the new authored catalogs (#1711).
"""

from __future__ import annotations

from django.contrib import admin

from world.battles.models import (
    Battle,
    BattleActionDeclaration,
    BattleParticipant,
    BattlePlace,
    BattleRound,
    BattleSide,
    BattleUnit,
    TechniqueCompositionAffinity,
    TerrainCompositionEffect,
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


@admin.register(BattlePlace)
class BattlePlaceAdmin(admin.ModelAdmin):
    list_display = ("battle", "name", "terrain_type", "movement_cost")
    list_filter = ("terrain_type",)


@admin.register(BattleUnit)
class BattleUnitAdmin(admin.ModelAdmin):
    list_display = (
        "battle",
        "name",
        "composition",
        "quality",
        "commander",
        "strength",
        "status",
    )
    list_filter = ("composition", "quality", "status")
    search_fields = ("name", "descriptor")
    autocomplete_fields = ("commander", "summoned_by")


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


@admin.register(TechniqueCompositionAffinity)
class TechniqueCompositionAffinityAdmin(admin.ModelAdmin):
    list_display = ("technique", "composition", "modifier")
    list_filter = ("composition",)
    autocomplete_fields = ("technique",)


@admin.register(TerrainCompositionEffect)
class TerrainCompositionEffectAdmin(admin.ModelAdmin):
    list_display = ("terrain_type", "composition", "modifier")
    list_filter = ("terrain_type", "composition")
