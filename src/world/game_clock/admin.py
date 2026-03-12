"""Admin interface for the game clock system."""

from django.contrib import admin

from world.game_clock.models import GameClock, GameClockHistory


@admin.register(GameClock)
class GameClockAdmin(admin.ModelAdmin):
    """Admin for the game clock singleton."""

    list_display = ["__str__", "anchor_ic_time", "time_ratio", "paused"]
    readonly_fields = ["anchor_real_time", "anchor_ic_time"]

    def has_add_permission(self, _request):
        """Prevent adding via admin — use set_clock() service."""
        return not GameClock.objects.exists()

    def has_delete_permission(self, _request, _obj=None):
        """Prevent deletion via admin."""
        return False


@admin.register(GameClockHistory)
class GameClockHistoryAdmin(admin.ModelAdmin):
    """Admin for clock change audit log."""

    list_display = [
        "changed_at",
        "changed_by",
        "old_anchor_ic_time",
        "new_anchor_ic_time",
        "old_time_ratio",
        "new_time_ratio",
        "reason",
    ]
    list_filter = ["changed_by"]
    readonly_fields = [
        "changed_by",
        "changed_at",
        "old_anchor_real_time",
        "old_anchor_ic_time",
        "old_time_ratio",
        "new_anchor_real_time",
        "new_anchor_ic_time",
        "new_time_ratio",
        "reason",
    ]

    def has_add_permission(self, _request):
        """History entries are created by services, not manually."""
        return False

    def has_delete_permission(self, _request, _obj=None):
        """Audit log should not be deleted."""
        return False
