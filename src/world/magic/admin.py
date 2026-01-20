from django.contrib import admin

from world.magic.models import Affinity, Resonance


@admin.register(Affinity)
class AffinityAdmin(admin.ModelAdmin):
    list_display = ["name", "affinity_type"]
    search_fields = ["name", "description"]
    readonly_fields = ["affinity_type"]  # Type shouldn't change after creation


@admin.register(Resonance)
class ResonanceAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "default_affinity"]
    list_filter = ["default_affinity"]
    search_fields = ["name", "slug", "description"]
    prepopulated_fields = {"slug": ("name",)}
