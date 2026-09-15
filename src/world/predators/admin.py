"""Admin for the `predators` app (#3831)."""

from django.contrib import admin

from world.predators.models import PredatorKind


@admin.register(PredatorKind)
class PredatorKindAdmin(admin.ModelAdmin):
    """#3831 - authored predator vocabulary: bandit company, pirate fleet, raider warband."""

    list_display = ["name", "base_strength", "weeks_per_stage_override"]
    search_fields = ["name", "description"]
