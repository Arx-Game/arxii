from django.contrib import admin

from world.magic.models import Affinity


@admin.register(Affinity)
class AffinityAdmin(admin.ModelAdmin):
    list_display = ["name", "affinity_type"]
    search_fields = ["name", "description"]
    readonly_fields = ["affinity_type"]  # Type shouldn't change after creation
