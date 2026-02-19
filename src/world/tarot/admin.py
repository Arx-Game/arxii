"""Django admin interface for the tarot system."""

from django.contrib import admin

from world.tarot.models import NamingRitualConfig, TarotCard


@admin.register(TarotCard)
class TarotCardAdmin(admin.ModelAdmin):
    list_display = ["name", "arcana_type", "suit", "rank", "latin_name"]
    list_filter = ["arcana_type", "suit"]
    search_fields = ["name", "latin_name"]


@admin.register(NamingRitualConfig)
class NamingRitualConfigAdmin(admin.ModelAdmin):
    list_display = ["flavor_text_preview", "codex_entry"]
    autocomplete_fields = ["codex_entry"]

    PREVIEW_MAX_LENGTH = 80

    def flavor_text_preview(self, obj: NamingRitualConfig) -> str:
        if len(obj.flavor_text) > self.PREVIEW_MAX_LENGTH:
            return obj.flavor_text[: self.PREVIEW_MAX_LENGTH] + "..."
        return obj.flavor_text

    flavor_text_preview.short_description = "Flavor Text"  # type: ignore[attr-defined]

    def has_add_permission(self, _request, _obj=None) -> bool:
        # Only allow adding if none exists (singleton pattern)
        return not NamingRitualConfig.objects.exists()
