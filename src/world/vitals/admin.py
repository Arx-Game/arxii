from django.contrib import admin

from world.vitals.models import CharacterVitals, VitalsConsequenceConfig


@admin.register(CharacterVitals)
class CharacterVitalsAdmin(admin.ModelAdmin):
    list_display = ["character_sheet", "health", "max_health", "life_state", "died_at"]
    list_filter = ["life_state"]
    search_fields = ["character_sheet__character__db_key"]


@admin.register(VitalsConsequenceConfig)
class VitalsConsequenceConfigAdmin(admin.ModelAdmin):
    """Singleton (pk=1) — global fallback consequence pools for survivability.

    knockout_pool fires when a character is knocked out (damage-type-agnostic).
    default_wound_pool / default_death_pool are the fallbacks used when a
    DamageType doesn't specify its own wound_pool / death_pool. Leaving a slot
    null makes that branch skip silently.
    """

    list_display = [
        "pk",
        "knockout_pool",
        "default_wound_pool",
        "default_death_pool",
        "updated_at",
    ]
    autocomplete_fields = ["knockout_pool", "default_wound_pool", "default_death_pool"]

    def has_add_permission(self, request: object) -> bool:  # noqa: ARG002
        """Prevent adding a second config — there can be only one."""
        return not VitalsConsequenceConfig.objects.exists()
