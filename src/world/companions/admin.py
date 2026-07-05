from django.contrib import admin

from world.companions.models import Companion, CompanionArchetype


@admin.register(CompanionArchetype)
class CompanionArchetypeAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "domain",
        "bind_difficulty",
        "capacity_cost",
        "max_health",
        "soak_value",
        "tier",
        "strength",
    ]
    list_filter = ["domain"]
    search_fields = ["name"]
    ordering = ["domain", "name"]


@admin.register(Companion)
class CompanionAdmin(admin.ModelAdmin):
    list_display = ["name", "archetype", "owner", "bonded_at", "released_at"]
    list_filter = ["archetype__domain"]
    search_fields = ["name"]
    autocomplete_fields = ["owner", "archetype", "granting_gift"]
