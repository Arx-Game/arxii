"""Django admin for tavern games (#3292)."""

from django.contrib import admin

from world.tavern_games.models import (
    GamblingLossLedger,
    GameSeat,
    GameSession,
    TavernGamblingConfig,
    TavernGame,
)


@admin.register(TavernGame)
class TavernGameAdmin(admin.ModelAdmin):
    list_display = ["name", "resolution_kind", "min_ante", "max_ante", "is_active"]
    search_fields = ["name"]
    list_filter = ["resolution_kind", "is_active"]


@admin.register(TavernGamblingConfig)
class TavernGamblingConfigAdmin(admin.ModelAdmin):
    list_display = ["weekly_loss_cap"]

    def has_add_permission(self, request) -> bool:  # noqa: ARG002
        """Singleton - no adding a second row via admin."""
        return not TavernGamblingConfig.objects.exists()


class GameSeatInline(admin.TabularInline):
    model = GameSeat
    extra = 0
    readonly_fields = ["persona", "ante_paid", "roll_result", "seated_at"]


@admin.register(GameSession)
class GameSessionAdmin(admin.ModelAdmin):
    autocomplete_fields = ["place", "opened_by"]
    list_display = ["game", "place", "state", "ante", "pot", "opened_by", "opened_at"]
    list_filter = ["state", "game"]
    search_fields = ["place__name"]
    inlines = [GameSeatInline]


@admin.register(GamblingLossLedger)
class GamblingLossLedgerAdmin(admin.ModelAdmin):
    autocomplete_fields = ["character_sheet"]
    list_display = ["character_sheet", "game_week", "total_lost"]
    list_filter = ["game_week"]
