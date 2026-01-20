from django.contrib import admin

from world.magic.models import (
    Affinity,
    CharacterAura,
    CharacterGift,
    CharacterPower,
    CharacterResonance,
    Gift,
    IntensityTier,
    Power,
    Resonance,
)


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


@admin.register(CharacterAura)
class CharacterAuraAdmin(admin.ModelAdmin):
    list_display = ["character", "celestial", "primal", "abyssal", "get_dominant"]
    list_filter = ["updated_at"]
    search_fields = ["character__db_key"]
    readonly_fields = ["updated_at"]

    @admin.display(description="Dominant")
    def get_dominant(self, obj):
        return obj.dominant_affinity.label


@admin.register(CharacterResonance)
class CharacterResonanceAdmin(admin.ModelAdmin):
    list_display = ["character", "resonance", "scope", "strength", "is_active"]
    list_filter = ["resonance", "scope", "strength", "is_active"]
    search_fields = ["character__db_key", "resonance__name"]
    autocomplete_fields = ["resonance"]


# =============================================================================
# Phase 2: Gifts & Powers Admin
# =============================================================================


@admin.register(IntensityTier)
class IntensityTierAdmin(admin.ModelAdmin):
    list_display = ["name", "threshold", "control_modifier"]
    ordering = ["threshold"]


@admin.register(Gift)
class GiftAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "affinity", "level_requirement"]
    list_filter = ["affinity", "level_requirement"]
    search_fields = ["name", "slug", "description"]
    prepopulated_fields = {"slug": ("name",)}
    filter_horizontal = ["resonances"]


@admin.register(Power)
class PowerAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "gift",
        "affinity",
        "base_intensity",
        "base_control",
        "anima_cost",
        "level_requirement",
    ]
    list_filter = ["gift", "affinity", "level_requirement"]
    search_fields = ["name", "slug", "description"]
    prepopulated_fields = {"slug": ("name",)}
    filter_horizontal = ["resonances"]
    autocomplete_fields = ["gift"]


@admin.register(CharacterGift)
class CharacterGiftAdmin(admin.ModelAdmin):
    list_display = ["character", "gift", "acquired_at"]
    list_filter = ["gift", "acquired_at"]
    search_fields = ["character__db_key", "gift__name"]
    autocomplete_fields = ["gift"]


@admin.register(CharacterPower)
class CharacterPowerAdmin(admin.ModelAdmin):
    list_display = ["character", "power", "times_used", "unlocked_at"]
    list_filter = ["power__gift", "unlocked_at"]
    search_fields = ["character__db_key", "power__name"]
    autocomplete_fields = ["power"]
