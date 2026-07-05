from django.contrib import admin

from world.companions.models import Companion, CompanionArchetype, CompanionDeployment


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


@admin.register(CompanionDeployment)
class CompanionDeploymentAdmin(admin.ModelAdmin):
    list_display = ["companion", "battle", "vehicle", "created_at"]
    list_filter = ["battle"]
    autocomplete_fields = ["companion"]
