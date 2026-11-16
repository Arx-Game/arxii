from django.contrib import admin

from world.fatigue.models import FatigueConfig, FatiguePool


@admin.register(FatiguePool)
class FatiguePoolAdmin(admin.ModelAdmin):
    autocomplete_fields = ["character_sheet"]
    list_display = [
        "character_sheet",
        "physical_current",
        "social_current",
        "mental_current",
        "well_rested",
    ]
    list_filter = ["well_rested", "rested_today", "dawn_deferred"]


@admin.register(FatigueConfig)
class FatigueConfigAdmin(admin.ModelAdmin):
    """The stat terms of fatigue capacity (#5093).

    A singleton at pk 1: one row, never added or deleted. The per-level bonus is the
    "Fatigue level bonus" lane of the modifier level baselines.
    """

    list_display = ["stat_multiplier", "willpower_multiplier", "well_rested_percent"]

    def has_add_permission(self, request: object) -> bool:  # noqa: ARG002
        """Prevent adding a second row; this is a pk=1 singleton."""
        return not FatigueConfig.objects.exists()

    def has_delete_permission(self, request: object, obj: object = None) -> bool:  # noqa: ARG002
        """The singleton is never deleted."""
        return False
