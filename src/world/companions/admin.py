from django.contrib import admin

from world.companions.models import (
    Companion,
    CompanionAbility,
    CompanionArchetype,
    CompanionDeployment,
    CompanionOrder,
)


class CompanionAbilityInline(admin.TabularInline):
    model = CompanionAbility
    extra = 0
    list_display = ["name", "ability_kind", "base_damage"]


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
    inlines = [CompanionAbilityInline]


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


@admin.register(CompanionOrder)
class CompanionOrderAdmin(admin.ModelAdmin):
    list_display = ["companion", "order_kind", "round_number", "encounter", "battle", "created_at"]
    list_filter = ["order_kind"]
    autocomplete_fields = ["companion"]
    readonly_fields = ["created_at"]
