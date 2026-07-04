from django.contrib import admin

from world.companions.models import CompanionArchetype


@admin.register(CompanionArchetype)
class CompanionArchetypeAdmin(admin.ModelAdmin):
    list_display = ["name", "domain", "bind_difficulty", "capacity_cost"]
    list_filter = ["domain"]
    search_fields = ["name"]
    ordering = ["domain", "name"]
